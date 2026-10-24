#!/usr/bin/env python3
"""
init_skill.py — 快速生成 skill 模板骨架

用法:
    python init_skill.py <skill-name> [--display-name "显示名"] [--description "描述"]
                         [--purpose "用途"] [--instructions "指令"] [--dir <目标目录>]

示例:
    python init_skill.py my-new-skill --display-name "我的新技能" --description "处理XXX任务"
    python init_skill.py pdf-helper --dir /path/to/installed_skill

生成的目录结构:
    <skill-name>/
    ├── SKILL.md          （含 frontmatter + 模板内容）
    ├── agents/           （可选的 agent 子指令）
    ├── scripts/          （可选的脚本资源）
    ├── references/       （可选的参考文档）
    └── assets/           （可选的静态资源）

注意:
    - 默认写入路径为本脚本所在 skill-creator 的上一级目录（即 installed_skill/）
    - 也可通过 --dir 显式指定目标目录
    - skill 名称须为小写字母、数字、连字符
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime


# skill-creator/scripts/ -> skill-creator/ -> installed_skill/
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_CREATOR_DIR = os.path.dirname(_SCRIPTS_DIR)
DEFAULT_INSTALLED_SKILL_DIR = os.path.dirname(_SKILL_CREATOR_DIR)

SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")

SKILL_MD_TEMPLATE = """---
name: {skill_name}
description: {description}
---

# {display_name}

## When to use this skill

- "{trigger_1}"
- "{trigger_2}"

## Purpose

{purpose}

## Instructions

{instructions}
"""

DEFAULT_TRIGGERS = {
    "zh": ("用户提到相关需求时", "当需要执行相关任务时"),
    "en": ("When user mentions related needs", "When relevant tasks need to be performed"),
}

DEFAULT_PURPOSE = {
    "zh": "（在此描述该 skill 的核心用途与适用场景）",
    "en": "(Describe the core purpose and applicable scenarios of this skill here)",
}

DEFAULT_INSTRUCTIONS = {
    "zh": """1. 确认用户意图与输入
2. 按步骤执行核心逻辑
3. 返回清晰、可操作的结果

> 提示：可在 `agents/` 下放子 agent 指令，在 `scripts/` 下放可执行脚本，在 `references/` 下放参考文档。""",
    "en": """1. Confirm user intent and inputs
2. Execute core logic step by step
3. Return clear, actionable results

> Tip: put sub-agent instructions under `agents/`, scripts under `scripts/`, and docs under `references/`.""",
}

GITKEEP = "# placeholder — keep this directory in version control\n"


def _detect_lang(text: str) -> str:
    """粗略判断中英文。"""
    if not text:
        return "zh"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cjk > 0 else "en"


def validate_skill_name(name: str) -> str | None:
    """校验 skill 名称，合法返回 None，否则返回错误信息。"""
    if not name or not name.strip():
        return "skill 名称不能为空"
    name = name.strip()
    if not SKILL_NAME_RE.match(name):
        return (
            f"非法 skill 名称: '{name}'。"
            "仅允许小写字母、数字、连字符，且须以字母或数字开头"
        )
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return f"非法 skill 名称: '{name}'。不能以连字符开头/结尾，也不能包含连续连字符"
    if len(name) > 64:
        return f"skill 名称过长（{len(name)} > 64）"
    return None


def build_skill_md(
    skill_name: str,
    description: str,
    display_name: str = "",
    purpose: str = "",
    instructions: str = "",
    skill_md_content: str = "",
) -> str:
    """生成 SKILL.md 正文。若提供 skill_md_content 则直接使用。"""
    if skill_md_content and skill_md_content.strip():
        content = skill_md_content.strip() + "\n"
        # 确保 frontmatter 中 name 与目录名一致
        if not content.startswith("---"):
            content = (
                f"---\nname: {skill_name}\n"
                f"description: {description or skill_name}\n---\n\n{content}"
            )
        return content

    lang = _detect_lang(description or display_name or purpose)
    t1, t2 = DEFAULT_TRIGGERS[lang]
    display = (display_name or skill_name).strip()
    desc = (description or f"Skill: {skill_name}").strip()
    purp = (purpose or DEFAULT_PURPOSE[lang]).strip()
    instr = (instructions or DEFAULT_INSTRUCTIONS[lang]).strip()

    return SKILL_MD_TEMPLATE.format(
        skill_name=skill_name,
        description=desc,
        display_name=display,
        trigger_1=t1,
        trigger_2=t2,
        purpose=purp,
        instructions=instr,
    )


def create_skill_skeleton(
    skill_name: str,
    description: str = "",
    display_name: str = "",
    purpose: str = "",
    instructions: str = "",
    skill_md_content: str = "",
    target_dir: str | None = None,
    overwrite: bool = False,
) -> dict:
    """
    在 target_dir（默认 installed_skill/）下创建 skill 骨架。

    返回:
        {
          "ok": bool,
          "skill_name": str,
          "path": str,           # skill 根目录绝对路径
          "skill_md": str,       # SKILL.md 绝对路径
          "created": list[str],  # 新建的路径列表
          "message": str,
          "error": str | None,
        }
    """
    err = validate_skill_name(skill_name)
    if err:
        return {
            "ok": False,
            "skill_name": skill_name,
            "path": "",
            "skill_md": "",
            "created": [],
            "message": "",
            "error": err,
        }

    skill_name = skill_name.strip()
    base = os.path.abspath(target_dir or DEFAULT_INSTALLED_SKILL_DIR)
    skill_path = os.path.join(base, skill_name)

    if os.path.exists(skill_path) and not overwrite:
        return {
            "ok": False,
            "skill_name": skill_name,
            "path": skill_path,
            "skill_md": "",
            "created": [],
            "message": "",
            "error": f"skill 目录已存在: {skill_path}（使用 --overwrite 可覆盖 SKILL.md）",
        }

    created: list[str] = []
    os.makedirs(skill_path, exist_ok=True)
    if skill_path not in created:
        created.append(skill_path)

    for sub in ("agents", "scripts", "references", "assets"):
        sub_path = os.path.join(skill_path, sub)
        os.makedirs(sub_path, exist_ok=True)
        created.append(sub_path)
        gitkeep_path = os.path.join(sub_path, ".gitkeep")
        if not os.path.exists(gitkeep_path):
            with open(gitkeep_path, "w", encoding="utf-8") as f:
                f.write(GITKEEP)
            created.append(gitkeep_path)

    md_body = build_skill_md(
        skill_name=skill_name,
        description=description,
        display_name=display_name,
        purpose=purpose,
        instructions=instructions,
        skill_md_content=skill_md_content,
    )
    skill_md_path = os.path.join(skill_path, "SKILL.md")
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(md_body)
    created.append(skill_md_path)

    # 可选：写一个简单的 README 帮助后续开发
    readme_path = os.path.join(skill_path, "README.md")
    if not os.path.exists(readme_path):
        readme = (
            f"# {display_name or skill_name}\n\n"
            f"{description or ''}\n\n"
            f"Created at {datetime.now().isoformat(timespec='seconds')}\n\n"
            f"## Structure\n\n"
            f"- `SKILL.md` — skill 主指令（frontmatter + body）\n"
            f"- `agents/` — 子 agent 指令\n"
            f"- `scripts/` — 可执行脚本\n"
            f"- `references/` — 参考文档\n"
            f"- `assets/` — 静态资源\n"
        )
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme)
        created.append(readme_path)

    return {
        "ok": True,
        "skill_name": skill_name,
        "path": skill_path,
        "skill_md": skill_md_path,
        "created": created,
        "message": f"Skill '{skill_name}' 骨架已创建于 {skill_path}",
        "error": None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a new skill skeleton under installed_skill/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("name", help="Skill identifier (lowercase-hyphens)")
    parser.add_argument(
        "--description",
        "-d",
        default="",
        help="Short description for frontmatter",
    )
    parser.add_argument(
        "--display-name",
        default="",
        help="Human-readable display name",
    )
    parser.add_argument(
        "--purpose",
        default="",
        help="Purpose section content",
    )
    parser.add_argument(
        "--instructions",
        default="",
        help="Instructions section content",
    )
    parser.add_argument(
        "--dir",
        default=None,
        help=f"Target parent directory (default: {DEFAULT_INSTALLED_SKILL_DIR})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite SKILL.md if skill directory already exists",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print result as JSON",
    )
    # 兼容旧用法: python init_skill.py name "description"
    parser.add_argument(
        "description_pos",
        nargs="?",
        default=None,
        help=argparse.SUPPRESS,
    )

    args = parser.parse_args(argv)

    description = args.description or args.description_pos or ""

    result = create_skill_skeleton(
        skill_name=args.name,
        description=description,
        display_name=args.display_name,
        purpose=args.purpose,
        instructions=args.instructions,
        target_dir=args.dir,
        overwrite=args.overwrite,
    )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print(result["message"])
            print(f"  SKILL.md: {result['skill_md']}")
            for p in result["created"]:
                print(f"  + {p}")
        else:
            print(f"ERROR: {result['error']}", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())