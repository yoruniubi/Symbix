# 扫描/加载已安装的 skill
import os

class SkillRegistry:
    def __init__(self, skill_directory: str = "skills"):
        self.skill_directory = skill_directory
        self.skills = {}
        self._scan_skills()

    def _scan_skills(self):
        if not os.path.exists(self.skill_directory):
            os.makedirs(self.skill_directory)
        for skill_name in os.listdir(self.skill_directory):
            skill_path = os.path.join(self.skill_directory, skill_name)
            if os.path.isdir(skill_path):
                self.skills[skill_name] = skill_path

    def get_skill_path(self, skill_name: str) -> str:
        return self.skills.get(skill_name, None)

    def list_skills(self):
        return list(self.skills.keys())