"""
Symbix SDK - Skill 模块
负责本地能力的加载、解析与生命周期管理
"""

from .loader import SkillLoader  # 假设你的 SkillLoader 类写在 loader.py 里面
from .registry import SkillRegistry
# 定义对外暴露的接口，这样别人 from Symbix_sdk.skill import * 时只会导入这些
__all__ = [
    "SkillLoader",
    "SkillRegistry"
]