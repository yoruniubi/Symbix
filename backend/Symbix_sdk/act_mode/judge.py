from dataclasses import dataclass
from enum import Enum
import re

class Mode(Enum):
    REACTIVE = "reactive"
    PLAN_SOLVE = "plan_solve"

@dataclass
class Judgment:
    emotion: str
    intensity: float
    mode: Mode
    reason: str

class Judge:
    """决定本轮采用哪条行为路线。

    Judge 不额外请求 LLM。它位于正式模型调用之前,使用可解释的信号完成
    路由,避免每轮对话多一次请求,也避免 Judge 与真正执行工具的模型产生
    两套互相竞争的决策。
    """
    def __init__(self, llm_client=None, intensity_threshold: float = 0.7):
        self.llm = llm_client
        self.intensity_threshold = intensity_threshold

    def judge(self, user_input: str, history: list = None) -> Judgment:
        text = (user_input or "").strip()
        lowered = text.lower()
        history = history or []

        complex_patterns = (
            r"\b(implement|refactor|debug|build|create|modify|fix|analy[sz]e|compare)\b",
            r"(实现|开发|重构|调试|修复|创建|修改|分析|比较|设计|整理|部署|测试)",
            r"(文件|代码|项目|仓库|git|api|数据库|工具|skill|mcp)",
        )
        signals = sum(bool(re.search(pattern, lowered if pattern.startswith(r"\b") else text, re.I))
                       for pattern in complex_patterns)
        numbered = len(re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+", text))
        asks_for_steps = bool(re.search(r"(步骤|计划|逐步|一步一步|how to|step by step)", text, re.I))
        intensity = min(1.0, 0.25 + 0.12 * signals + 0.1 * numbered + (0.2 if asks_for_steps else 0))
        is_complex = signals >= 1 or numbered >= 2 or asks_for_steps or len(text) > 500
        emotion = "frustrated" if re.search(r"(急|卡|报错|失败|不行|烦|error|fail|broken)", text, re.I) else "neutral"
        reason = "需要拆解多个步骤或使用工具" if is_complex else "单轮问题可直接回应"
        mode = Mode.PLAN_SOLVE if is_complex or intensity >= self.intensity_threshold else Mode.REACTIVE
        return Judgment(
            emotion=emotion,
            intensity=round(intensity, 2),
            mode=mode,
            reason=reason,
        )