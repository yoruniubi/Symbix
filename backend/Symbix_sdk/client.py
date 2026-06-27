import litellm
from typing import AsyncGenerator, Optional

from backend.Symbix_sdk.skill import SkillLoader
from backend.Symbix_sdk.skill.registry import SkillRegistry
from .providers import ProviderRegistry

class SymbixClient:
    """统一的 AI 调用客户端，封装 litellm，管理 provider 切换"""

    def __init__(self, registry: ProviderRegistry, system_prompt: str = ""):
        self.registry = registry
        self.system_prompt = system_prompt
        litellm.drop_params = True  # 不支持的参数自动丢弃，避免报错

    def _build_messages(self, history, user_input, registry=None):
        messages = []
        system = self.system_prompt
        if registry:
            system += registry.inject_relevant(user_input)  # 自动注入匹配的 skill
        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        return messages

    async def chat_stream(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """流式对话，逐字 yield"""
        provider = self.registry.get_active()
        messages = self._build_messages(history or [], user_input)

        kwargs = {
            "model": provider.model,
            "messages": messages,
            "stream": True,
        }
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.api_base:
            kwargs["api_base"] = provider.api_base
        if tools:
            kwargs["tools"] = tools

        response = await litellm.acompletion(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def chat(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """非流式对话，返回完整响应（含 tool_calls）"""
        provider = self.registry.get_active()
        messages = self._build_messages(history or [], user_input)

        kwargs = {
            "model": provider.model,
            "messages": messages,
        }
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if provider.api_base:
            kwargs["api_base"] = provider.api_base
        if tools:
            kwargs["tools"] = tools

        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "tool_calls": message.tool_calls,
            "model": response.model,
        }