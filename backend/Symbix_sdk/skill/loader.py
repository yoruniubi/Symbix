# skills/loader.py
from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SkillInfo:
    name: str                    # 文件夹名，即 skill id
    path: str                    # 完整路径
    display_name: str = ""       # 从 SKILL.md 第一个 # 标题提取
    description: str = ""        # Purpose 段落内容
    trigger_keywords: list[str] = field(default_factory=list)  # When to use 段落
    skill_md_content: str = ""   # 完整原文，给 LLM 注入用

class SkillLoader:
    """解析单个 skill 目录，提取元数据"""

    def load(self, skill_path: str) -> Optional[SkillInfo]:
        skill_md_path = os.path.join(skill_path, "SKILL.md")
        if not os.path.exists(skill_md_path):
            return None

        with open(skill_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        skill_name = os.path.basename(skill_path)

        return SkillInfo(
            name=skill_name,
            path=skill_path,
            display_name=self._extract_title(content),
            description=self._extract_section(content, "Purpose"),
            trigger_keywords=self._extract_triggers(content),
            skill_md_content=content,
        )

    def _extract_title(self, content: str) -> str:
        """提取第一个 # 标题"""
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def _extract_section(self, content: str, section_name: str) -> str:
        """提取指定二级标题下的内容，到下一个二级标题截止"""
        pattern = rf"## {section_name}\s*\n(.*?)(?=\n## |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_triggers(self, content: str) -> list[str]:
        """从 When to use 段落里提取触发关键词列表"""
        section = self._extract_section(content, "When to use this skill")
        # 提取引号内的触发短语
        quoted = re.findall(r'"([^"]+)"', section)
        if quoted:
            return quoted
        # fallback：提取每行 - 开头的条目
        lines = [
            line.lstrip("- ").strip()
            for line in section.splitlines()
            if line.strip().startswith("-")
        ]
        return lines
