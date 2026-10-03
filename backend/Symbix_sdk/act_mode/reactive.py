class ReactiveAgent:
    """Reactive 路径下生成第一笔简短响应。

    直接复用 llm_client.chat(...)（已经是异步实现），避免调一个并不存在的独立 generate() 接口。
    """

    def __init__(self, llm_client):
        self.llm = llm_client

    async def act(self, user_input: str, judgment, history: list = None) -> str:
        history = history or []
        prompt = (
            f"You are responding to someone expressing {judgment.emotion} "
            f"(intensity {judgment.intensity}).\n"
            "Give a brief, emotionally attuned response. "
            "Don't over-analyze — respond naturally.\n\n"
            f"Message: {user_input}"
        )
        result = await self.llm.chat(
            user_input=prompt,
            history=history,
            registry=None,
            tools=None,
        )
        # 上游报错时 content 为空,记日志避免「空回复」被当成正常结果
        if result.get("error") and not (result.get("content") or "").strip():
            print(f"[ActMode] reactive 上游报错: {result['error']}")
        return result.get("content") or ""