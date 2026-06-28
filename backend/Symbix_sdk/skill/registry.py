from __future__ import annotations 
import os
from .loader import SkillLoader, SkillInfo

class SkillRegistry:
    """扫描已安装的 skill，提供查询和注入接口"""

    def __init__(self, skills_dir: str = "skills/installed"):
        self.skills_dir = skills_dir
        self._loader = SkillLoader()
        self._skills: dict[str, SkillInfo] = {}
        self.scan()

    def scan(self):
        """重新扫描 installed 目录"""
        self._skills.clear()
        if not os.path.exists(self.skills_dir):
            os.makedirs(self.skills_dir)
            return
        for name in os.listdir(self.skills_dir):
            path = os.path.join(self.skills_dir, name)
            if not os.path.isdir(path):
                continue
            info = self._loader.load(path)
            if info:
                self._skills[name] = info

    def list(self) -> list[SkillInfo]:
        return list(self._skills.values())

    def get(self, name: str) -> SkillInfo | None:
        return self._skills.get(name)

    def find_by_trigger(self, user_input: str) -> list[SkillInfo]:
        """根据用户输入匹配可能相关的 skill"""
        matched = []
        lower_input = user_input.lower()
        for skill in self._skills.values():
            for kw in skill.trigger_keywords:
                if kw.lower() in lower_input:
                    matched.append(skill)
                    break
        return matched

    def inject_into_prompt(self, skill_name: str) -> str:
        """返回可直接注入 system prompt 的 skill 内容"""
        skill = self.get(skill_name)
        if not skill:
            return ""
        return f"\n\n<skill name='{skill.display_name}'>\n{skill.skill_md_content}\n</skill>"

    def inject_relevant(self, user_input: str) -> str:
        """根据输入自动匹配并注入相关 skill"""
        matched = self.find_by_trigger(user_input)
        if not matched:
            return ""
        return "".join(self.inject_into_prompt(s.name) for s in matched)