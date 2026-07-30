# tools/skill_tools.py
"""Skill 创建工具：create_skill + 辅助函数"""
from __future__ import annotations
import json
import os
import re


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


def _slugify_skill_name(name: str) -> str:
    """将名称规范为英文小写 + 连字符的 skill 标识"""
    if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        return name
    result = re.sub(r"[\s_]+", "-", name.lower())
    result = re.sub(r"[^a-z0-9-]", "", result)
    return result.strip("-") or name


def _resolve_skills_dir(registry=None, default_dir: str = ".") -> str:
    """解析 skill 安装目录：优先用 SkillRegistry，否则用默认路径"""
    if registry and getattr(registry, "skills_dir", None):
        return os.path.abspath(registry.skills_dir)
    return os.path.abspath(default_dir)


def _run_create_skill_skeleton(
    skill_slug: str,
    description: str,
    display_name: str,
    purpose: str,
    instructions: str,
    skill_md_content: str,
    target_dir: str,
) -> dict:
    """调用 init_skill.create_skill_skeleton（通过 importlib 加载含连字符路径的模块）；
    加载失败时回退到内置实现。"""
    try:
        import importlib.util

        # 本文件位于 tools/，目标脚本在 skill/installed_skill/skill-creator/scripts/init_skill.py
        _TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
        init_path = os.path.join(
            _TOOLS_DIR,
            "..",
            "skill",
            "installed_skill",
            "skill-creator",
            "scripts",
            "init_skill.py",
        )
        init_path = os.path.normpath(init_path)
        if os.path.isfile(init_path):
            spec = importlib.util.spec_from_file_location("symbix_init_skill", init_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod.create_skill_skeleton(
                    skill_name=skill_slug,
                    description=description,
                    display_name=display_name,
                    purpose=purpose,
                    instructions=instructions,
                    skill_md_content=skill_md_content,
                    target_dir=target_dir,
                    overwrite=False,
                )
        raise FileNotFoundError(f"init_skill.py not found at {init_path}")
    except Exception as e:
        return _fallback_create_skill_skeleton(
            skill_slug=skill_slug,
            description=description,
            display_name=display_name,
            purpose=purpose,
            instructions=instructions,
            skill_md_content=skill_md_content,
            target_dir=target_dir,
            import_error=str(e),
        )


def _fallback_create_skill_skeleton(
    skill_slug: str,
    description: str,
    display_name: str,
    purpose: str,
    instructions: str,
    skill_md_content: str,
    target_dir: str,
    import_error: str = "",
) -> dict:
    """init_skill 不可用时的内置骨架创建逻辑。"""
    skill_dir = os.path.join(os.path.abspath(target_dir), skill_slug)
    if os.path.exists(os.path.join(skill_dir, "SKILL.md")):
        return {
            "ok": False,
            "skill_name": skill_slug,
            "path": skill_dir,
            "skill_md": "",
            "created": [],
            "message": "",
            "error": (
                f"Skill 已存在: {skill_dir}。"
                "如需修改请直接编辑 SKILL.md，或先删除后重建。"
            ),
        }

    created: list[str] = []
    os.makedirs(skill_dir, exist_ok=True)
    created.append(skill_dir)
    for sub in ("agents", "scripts", "references", "assets"):
        sub_path = os.path.join(skill_dir, sub)
        os.makedirs(sub_path, exist_ok=True)
        created.append(sub_path)

    if skill_md_content and skill_md_content.strip():
        content = skill_md_content.strip() + "\n"
        if not content.lstrip().startswith("---"):
            content = (
                f"---\nname: {skill_slug}\ndescription: {description}\n---\n\n"
                + content
            )
    else:
        purpose_text = purpose or (
            f"这个技能用于处理 {display_name} 相关的任务，帮助 agent 更高效地完成工作。"
        )
        instructions_text = instructions or (
            "1. 理解用户的需求和目标\n"
            "2. 根据 skill 的指引执行相应操作\n"
            "3. 向用户确认结果是否符合预期\n"
        )
        content = SKILL_MD_TEMPLATE.format(
            skill_name=skill_slug,
            description=description.strip(),
            display_name=display_name,
            trigger_1="用户提到相关需求时",
            trigger_2="当需要执行相关任务时",
            purpose=purpose_text,
            instructions=instructions_text,
        )

    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(content)
    created.append(skill_md_path)

    msg = f"Skill '{skill_slug}' 骨架已创建于 {skill_dir}"
    if import_error:
        msg += f"（init_skill 导入失败，已用内置模板: {import_error}）"

    return {
        "ok": True,
        "skill_name": skill_slug,
        "path": skill_dir,
        "skill_md": skill_md_path,
        "created": created,
        "message": msg,
        "error": None,
    }


def create_skill(
    skill_name: str,
    description: str,
    display_name: str = "",
    purpose: str = "",
    instructions: str = "",
    skill_md_content: str = "",
    reload: bool = True,
    _skill_registry=None,
    _default_skills_dir: str = ".",
    _on_skill_created=None,  # callback: fn() to re-register skills after creation
) -> str:
    """在 installed_skill/ 下创建完整 skill 骨架（类似 MCP installer）

    优先委托 skill-creator/scripts/init_skill.py 的 create_skill_skeleton，
    保证 CLI 与 native tool 使用同一套模板逻辑。

    目录结构:
        installed_skill/<skill_name>/
        ├── SKILL.md
        ├── agents/
        ├── scripts/
        ├── references/
        └── assets/

    Args:
        skill_name: skill 标识（英文小写+连字符）
        description: 简短描述（用于触发匹配，写入 frontmatter）
        display_name: 显示名称（中文友好名）
        purpose: 技能目的说明
        instructions: 给 agent 的操作指令
        skill_md_content: 若提供则直接作为完整 SKILL.md 内容（覆盖模板）
        reload: 创建后是否立即重新扫描并注册 skill

    Returns:
        JSON 字符串，含 status / path / skill_name / message
    """
    try:
        skill_slug = _slugify_skill_name((skill_name or "").strip())
        if not skill_slug:
            return json.dumps(
                {"status": "error", "message": "skill_name 不能为空"},
                ensure_ascii=False,
            )
        if not description or not str(description).strip():
            return json.dumps(
                {"status": "error", "message": "description 不能为空（用于触发匹配）"},
                ensure_ascii=False,
            )

        skills_dir = _resolve_skills_dir(_skill_registry, _default_skills_dir)
        result = _run_create_skill_skeleton(
            skill_slug=skill_slug,
            description=str(description).strip(),
            display_name=(display_name or skill_name or skill_slug).strip(),
            purpose=purpose or "",
            instructions=instructions or "",
            skill_md_content=skill_md_content or "",
            target_dir=skills_dir,
        )
        if not result.get("ok"):
            return json.dumps(
                {
                    "status": "error",
                    "skill_name": skill_slug,
                    "path": result.get("path") or "",
                    "message": result.get("error") or "创建 skill 失败",
                },
                ensure_ascii=False,
            )

        skill_dir = result["path"]
        skill_md_path = result["skill_md"]
        reloaded = False
        reload_error = None
        if reload and _skill_registry is not None:
            try:
                _skill_registry.scan()
                if _on_skill_created:
                    _on_skill_created()
                reloaded = True
            except Exception as e:
                reload_error = str(e)

        message = result.get("message") or f"Skill 骨架已创建: {skill_dir}"
        message += (
            "\n下一步: 编辑 SKILL.md 完善指令；"
            "需要时可在 agents/、scripts/、references/、assets/ 中补充资源。"
        )
        if reloaded:
            message += f" 已热加载并注册为 skill__{skill_slug} 工具。"
        elif reload_error:
            message += (
                f" 但热加载失败: {reload_error}。"
                "请调用 /skills/reload 或重启服务。"
            )

        return json.dumps(
            {
                "status": "ok",
                "skill_name": skill_slug,
                "path": os.path.abspath(skill_dir),
                "skill_md": os.path.abspath(skill_md_path) if skill_md_path else "",
                "created": result.get("created") or [],
                "reloaded": reloaded,
                "message": message,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"创建 skill 失败: {e}"},
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

SKILL_TOOLS_SCHEMAS = {
    "create_skill": {
        "func": create_skill,
        "description": (
            "创建新的 Agent Skill 骨架，写入 installed_skill/<skill_name>/ 目录。"
            "当用户要求创建 skill、生成技能模板、或 skill-creator 工作流需要初始化目录时调用。"
            "会自动生成 SKILL.md（含 frontmatter）以及 agents/、scripts/、references/、assets/ 子目录，"
            "并在创建后热加载注册。请勿在其他路径手动创建 skill。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Skill 标识名（英文小写+连字符，如 pdf-helper、code-reviewer）",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Skill 简短描述，写入 frontmatter，用于触发匹配。"
                        "应说明做什么、何时触发（WHAT + WHEN），第三人称。"
                    ),
                },
                "display_name": {
                    "type": "string",
                    "description": "显示名称（中文友好名），可选，默认等于 skill_name",
                },
                "purpose": {
                    "type": "string",
                    "description": "技能目的说明（写入 SKILL.md 的 Purpose 段落），可选",
                },
                "instructions": {
                    "type": "string",
                    "description": "给 agent 的操作指令正文（写入 SKILL.md 的 Instructions），可选",
                },
                "skill_md_content": {
                    "type": "string",
                    "description": (
                        "完整的 SKILL.md 内容。若提供则覆盖模板生成；"
                        "若无 frontmatter 会自动补上 name/description。"
                    ),
                },
                "reload": {
                    "type": "boolean",
                    "description": "创建后是否立即重新扫描并注册 skill，默认 true",
                    "default": True,
                },
            },
            "required": ["skill_name", "description"],
        },
    },
}