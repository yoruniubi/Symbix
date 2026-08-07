class ReactiveAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    def act(self, user_input: str, judgment, history: list = None) -> str:
        prompt = f"""You are responding to someone expressing {judgment.emotion} (intensity {judgment.intensity}).
Give a brief, emotionally attuned response. Don't over-analyze — respond naturally.

Message: {user_input}"""
        return self.llm.generate(prompt)