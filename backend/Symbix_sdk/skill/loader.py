# skills/loader.py
from __future__ import annotations
import os
import re
import yaml
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SkillInfo:
    name: str                    # 文件夹名，即 skill id
    path: str                    # 完整路径
    display_name: str = ""       # 从 frontmatter name 或 SKILL.md 第一个 # 标题提取
    description: str = ""        # frontmatter description 或 Purpose 段落内容
    trigger_keywords: list[str] = field(default_factory=list)  # 触发关键词
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

        # 解析 YAML frontmatter
        frontmatter = self._parse_frontmatter(content)
        fm_description = frontmatter.get("description", "")
        fm_name = frontmatter.get("name", "")

        # 尝试从 "When to use this skill" 段落提取触发关键词
        triggers = self._extract_triggers(content)

        # 如果没有找到 "When to use" 段落，从 frontmatter description 提取关键词
        if not triggers and fm_description:
            triggers = self._extract_keywords_from_description(fm_description)

        return SkillInfo(
            name=skill_name,
            path=skill_path,
            display_name=fm_name or self._extract_title(content),
            description=fm_description or self._extract_section(content, "Purpose"),
            trigger_keywords=triggers,
            skill_md_content=content,
        )

    def _parse_frontmatter(self, content: str) -> dict:
        """解析 YAML frontmatter (--- ... ---)"""
        match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
        if not match:
            return {}
        try:
            return yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            return {}

    def _extract_title(self, content: str) -> str:
        """提取第一个 # 标题（跳过 frontmatter）"""
        # 去掉 frontmatter 后再搜索
        body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, count=1, flags=re.DOTALL)
        match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
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

    def _extract_keywords_from_description(self, description: str) -> list[str]:
        """从 frontmatter description 中提取有意义的触发关键词/短语"""
        # 优先提取引号内的内容
        quoted = re.findall(r'"([^"]+)"', description)
        if quoted:
            return quoted

        # 按逗号和句号分割，提取有意义的关键短语
        parts = re.split(r'[,;.]\s*', description)
        keywords = []
        for p in parts:
            p = p.strip()
            # 跳过太短或太长的片段
            if 3 < len(p) < 80:
                keywords.append(p.lower())
        return keywords[:10]  # 限制最多 10 个关键词