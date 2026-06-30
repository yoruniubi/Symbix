import litellm
import json
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

    def _build_messages(self, history, user_input, registry=None, tools=None):
        messages = []
        system = self.system_prompt

        # 注入 Skill 相关内容到 system prompt
        if registry:
            skill_injection = registry.inject_relevant(user_input)
            system += skill_injection

        # 如果有 tools，在 system prompt 中添加工具使用说明
        if tools:
            tool_names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
            if tool_names:
                tool_instructions = (
                    "\n\n[工具使用说明]\n"
                    "你可以使用以下工具来完成任务。当需要执行操作时，"
                    "请直接调用相应的工具函数，而不是告诉用户你无法执行。\n"
                    f"可用工具: {', '.join(tool_names)}\n"
                    "工具描述:\n"
                )
                for t in tools:
                    if t.get("type") == "function":
                        f = t["function"]
                        tool_instructions += f"- {f['name']}: {f['description']}\n"
                system += tool_instructions

        if system:
            messages.append({"role": "system", "content": system})
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})
        return messages

    def _build_kwargs(self, model, custom_provider, api_base, api_key, messages, tools=None):
        """构建 litellm.acompletion 的通用 kwargs"""
        kwargs = {"model": model, "messages": messages}
        if api_key:
            kwargs["api_key"] = api_key
        if api_base:
            kwargs["api_base"] = api_base
        if custom_provider:
            kwargs["custom_llm_provider"] = custom_provider
        if tools:
            kwargs["tools"] = tools
        return kwargs

    async def chat_stream(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
        registry=None,
        override_api_key: str = None,
        override_api_base: str = None,
        override_model: str = None,
    ) -> AsyncGenerator[str, None]:
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        model, custom_provider, api_base = self._resolve_model(raw_model, raw_base)
        api_key = override_api_key or provider.api_key

        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools)

        kwargs = self._build_kwargs(model, custom_provider, api_base, api_key, messages, tools)

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

        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools)
        api_key = override_api_key or provider.api_key

        kwargs = self._build_kwargs(model, custom_provider, api_base, api_key, messages, tools)

        print(">>> api_key:", api_key[:10] + "..." if api_key else None)
        print(">>> api_base:", api_base)
        print(">>> model:", model)
        if tools:
            print(">>> tools count:", len(tools))
        
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "tool_calls": message.tool_calls,
            "model": response.model,
        }

    async def chat_with_tool_results(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
        registry=None,
        tool_results: list[dict] = None,
        override_api_key: str = None,
        override_api_base: str = None,
        override_model: str = None,
    ) -> dict:
        """将工具执行结果回传给 LLM，继续对话以获得最终回复
        
        Args:
            tool_results: 工具执行结果列表，每项包含 tool_call_id, role, name, content
        """
        provider = self.registry.get_active()

        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        model, custom_provider, api_base = self._resolve_model(raw_model, raw_base)
        api_key = override_api_key or provider.api_key

        # 构建包含工具结果的完整消息链
        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools)
        
        # 添加 assistant 的 tool_calls 消息
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tr["tool_call_id"],
                    "type": "function",
                    "function": {
                        "name": tr["name"],
                        "arguments": "{}",  # 已执行，参数不再重要
                    },
                }
                for tr in (tool_results or [])
            ],
        })
        
        # 添加每个工具的执行结果
        for tr in (tool_results or []):
            messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "name": tr["name"],
                "content": tr["content"],
            })

        kwargs = self._build_kwargs(model, custom_provider, api_base, api_key, messages, tools)

        print(">>> [tool_results] model:", model)
        if tools:
            print(">>> [tool_results] tools count:", len(tools))

        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "tool_calls": message.tool_calls,
            "model": response.model,
        }