# 解析SKILL.md + 执行脚本
import os
import re

class SkillLoader:
    def __init__(self, skill_directory: str = "skills"):
        self.skill_directory = skill_directory
        