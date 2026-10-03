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

    def inject_into_prompt(self, skill_name: str, max_bytes: int | None = None) -> str:
        """返回可注入模型的 skill 内容。

        max_bytes 给定时，指南超过该体积就不再整篇注入（如 skill-creator 33.6KB），
        改为明说「请用 `skill__<name>` 工具加载」，避免每轮白烧 token。
        """
        skill = self.get(skill_name)
        if not skill:
            return ""
        body = skill.skill_md_content or ""
        if max_bytes and len(body.encode("utf-8")) > max_bytes:
            return (
                f"\n- 技能 `{skill.name}`（指南较大，未直接注入）:"
                f"请先调用 `skill__{skill.name}` 加载完整指南，再按指南执行。\n"
            )
        return f"\n<skill name='{skill.display_name or skill.name}'>\n{body}\n</skill>"

    def inject_relevant(self, user_input: str, max_bytes: int | None = None) -> str:
        """根据输入自动匹配并注入相关 skill"""
        matched = self.find_by_trigger(user_input)
        if not matched:
            return ""
        return "".join(self.inject_into_prompt(s.name, max_bytes=max_bytes) for s in matched)

    def inject_skill_overview(self) -> str:
        """
        注入所有 skill 的概要信息
        即使没有匹配到具体 skill，也告诉模型有哪些技能可用
        """
        if not self._skills:
            return ""
        
        overview = "\n\n[可用技能列表]\n"
        overview += "你拥有以下技能，可以在适当时候使用：\n\n"
        
        for skill in self._skills.values():
            overview += f"- **{skill.display_name}** ({skill.name}): {skill.description}\n"
            if skill.trigger_keywords:
                keywords = ", ".join(f'"{kw}"' for kw in skill.trigger_keywords[:5])  # 只显示前5个
                overview += f"  触发关键词: {keywords}\n"
        
        overview += "\n当用户的请求与上述技能的描述或触发关键词匹配时,"
        overview += "请**主动调用对应的 `skill__<skill-name>` 工具**加载完整技能指南,"
        overview += "并严格遵循指南中的步骤与指令完成任务;不要只凭上方列表的简短描述猜测做法。\n"
        overview += (
            "技能指南返回时会附带该技能的文件清单;需要更多细节时,优先用 "
            "`skill__<skill-name>(search=\"关键词\")` 定位,再用 `section=\"标题\"` / "
            "`paths=[\"references/a.md#标题\"]` / `paths=[\"a.md:100-180\"]` 精读,"
            "或用 `paths=[\"references/a.md\", \"config/b.json\"]` **一次读多个文件**;"
            "不要逐个文件读,也不要用 read_file 猜技能目录里的路径。\n"
        )
        
        return overview