class PlanSolveAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    def plan(self, user_input: str, judgment, history: list) -> list[str]:
        """生成交给主模型执行的行为计划,不重复发起一套 LLM 对话。"""
        text = (user_input or "").lower()
        plan = ["理解用户目标、约束和已有上下文,不要重复询问已知信息"]
        if any(word in text for word in ("代码", "文件", "项目", "git", "api", "skill", "mcp")):
            plan.extend([
                "先检查相关文件和现有实现,再决定最小且兼容的修改",
                "需要行动时按顺序调用工具,根据工具结果决定下一步",
            ])
        else:
            plan.extend([
                "将问题拆成可验证的子目标,明确必要的假设",
                "给出可执行方案,并说明关键取舍或风险",
            ])
        plan.append("完成后回顾结果是否满足原始需求,如有遗漏再补救")
        return plan

    def solve(self, plan: list[str], user_input: str) -> str:
        return "\n".join(f"{index}. {step}" for index, step in enumerate(plan, 1))