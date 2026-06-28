import litellm
from typing import AsyncGenerator, Optional
from .skill import SkillLoader
from .skill.registry import SkillRegistry
from .providers import ProviderRegistry

class SymbixClient:
    def __init__(self, registry: ProviderRegistry, system_prompt: str = ""):
        self.registry = registry
        self.system_prompt = system_prompt
        litellm.drop_params = True

    def _resolve_model(self, model: str, api_base: str) -> tuple[str, str, str]:
        if api_base:
            # 去掉结尾斜杠
            api_base = api_base.rstrip('/')
            # 自动补 /v1
            if not api_base.endswith('/v1'):
                api_base = api_base + '/v1'
            # 去掉 openai/ 前缀，直接用裸模型名
            if model.startswith('openai/'):
                model = model[len('openai/'):]
            return model, 'openai', api_base
        return model, None, api_base

    def _build_messages(self, history, user_input, registry=None):
        messages = []
        system = self.system_prompt
        if registry:
            system += registry.inject_relevant(user_input)
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
        registry=None,
    ) -> AsyncGenerator[str, None]:
        provider = self.registry.get_active()
        messages = self._build_messages(history or [], user_input, registry=registry)
        model, custom_provider, api_base = self._resolve_model(provider.model, provider.api_base)

        kwargs = {
            "model": model,
            "messages": messages,
        }
        if provider.api_key:
            kwargs["api_key"] = provider.api_key
        if api_base:                          # ← 用 api_base 不用 provider.api_base
            kwargs["api_base"] = api_base
        if custom_provider:
            kwargs["custom_llm_provider"] = custom_provider
        if tools:
            kwargs["tools"] = tools

        print("chat_stream kwargs:", {k: v for k, v in kwargs.items() if k != "messages"})
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
        registry=None,
        override_api_key: str = None,
        override_api_base: str = None,
        override_model: str = None,
    ) -> dict:
        provider = self.registry.get_active()
        
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        model, custom_provider, api_base = self._resolve_model(raw_model, raw_base)

        messages = self._build_messages(history or [], user_input, registry=registry)
        kwargs = {"model": model, "messages": messages}
        
        api_key = override_api_key or provider.api_key
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base
        if custom_provider:
            kwargs["custom_llm_provider"] = custom_provider
        if tools:
            kwargs["tools"] = tools

        print(">>> api_key:", api_key[:10] + "..." if api_key else None)
        print(">>> api_base:", api_base)
        print(">>> model:", model)
        
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "tool_calls": message.tool_calls,
            "model": response.model,
        }