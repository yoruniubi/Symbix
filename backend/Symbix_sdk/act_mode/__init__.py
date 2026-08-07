from dataclasses import dataclass

from .judge import Judge, Judgment, Mode
from .reactive import ReactiveAgent
from .plan_solve import PlanSolveAgent

@dataclass
class ActDecision:
    judgment: Judgment
    plan: list[str]


class ActModeController:
    def __init__(self, llm_client):
        self.judge = Judge(llm_client)
        self.reactive = ReactiveAgent(llm_client)
        self.planner = PlanSolveAgent(llm_client)

    def decide(self, user_input: str, history: list = None) -> ActDecision:
        history = history or []
        judgment = self.judge.judge(user_input, history)
        plan = (
            self.planner.plan(user_input, judgment, history)
            if judgment.mode == Mode.PLAN_SOLVE
            else []
        )
        return ActDecision(judgment=judgment, plan=plan)

    def respond(self, user_input: str, history: list = None) -> str:
        """兼容旧调用方;新聊天链应使用 decide 后交给主模型执行。"""
        history = history or []
        decision = self.decide(user_input, history)
        if decision.judgment.mode == Mode.REACTIVE:
            return self.reactive.act(user_input, decision.judgment, history)
        return self.planner.solve(decision.plan, user_input)

__all__ = [
    "ActModeController",
    "ActDecision",
    "Judge",
    "Judgment",
    "Mode",
    "ReactiveAgent",
    "PlanSolveAgent",
]