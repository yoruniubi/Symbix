"""
SymbixClient — 核心 AI 对话客户端
流式路径绕过 litellm，直接用 HTTP SSE 请求上游 API
"""
import json
import httpx
from typing import AsyncGenerator, Optional
from .skill import SkillLoader
from .skill.registry import SkillRegistry
from .providers import ProviderRegistry


def _sanitize_tools(tools: list[dict]) -> list[dict]:
    """统一清洗 tool 列表，确保符合 OpenAI function-calling 严格 schema：
    - 顶层必须是 {"type": "function", "function": {...}}
    - parameters 必须是 {"type": "object", ...}，过滤 $ 开头元字段
    - 名字必填、非空
    异常工具会被静默丢弃，而不是让整次请求失败。
    """
    clean = []
    for t in tools or []:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not name or not isinstance(name, str):
            continue
        params = fn.get("parameters")
        if not isinstance(params, dict) or params.get("type") != "object":
            params = {"type": "object", "properties": {}}
        else:
            props = params.get("properties")
            if not isinstance(props, dict):
                props = {}
            else:
                clean_props = {}
                for p_name, p_schema in props.items():
                    if not isinstance(p_schema, dict):
                        continue
                    cp = {k: v for k, v in p_schema.items() if not k.startswith("$")}
                    if "type" not in cp and "anyOf" not in cp and "oneOf" not in cp:
                        cp = {"type": "string", **cp}
                    clean_props[p_name] = cp
                props = clean_props
            params = {
                "type": "object",
                "properties": props,
            }
            req = params.get("required")
            if isinstance(req, list):
                params["required"] = [r for r in req if isinstance(r, str)]
        clean.append({
            "type": "function",
            "function": {
                "name": name,
                "description": fn.get("description", "") or "",
                "parameters": params,
            },
        })
    return clean


class SymbixClient:
    def __init__(self, registry: ProviderRegistry, system_prompt: str = ""):
        self.registry = registry
        self.system_prompt = system_prompt

    # ── helper ─────────────────────────────────────────────────
    def _resolve_endpoint(self, model: str, api_base: str, api_key: str) -> tuple[str, str, dict]:
        """返回 (url, provider_type, headers)。
        provider_type ∈ {'anthropic', 'openai', 'custom_openai'}
        """
        if api_base:
            base = api_base.rstrip('/')
            if not base.endswith('/v1'):
                base = base + '/v1'
            # 自定义中转 → OpenAI 兼容格式
            model_name = model
            if model.startswith('openai/'):
                model_name = model[len('openai/'):]
            url = f"{base}/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            return url, "custom_openai", headers, model_name

        # 根据 litellm 前缀判断
        if model.startswith("anthropic/"):
            model_name = model[len("anthropic/"):]
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            }
            return url, "anthropic", headers, model_name

        if model.startswith("gemini/"):
            model_name = model[len("gemini/"):]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={api_key}"
            headers = {"Content-Type": "application/json"}
            return url, "gemini", headers, model_name

        # Groq / Mistral / DeepSeek 等 — OpenAI 兼容
        if model.startswith("groq/"):
            model_name = model[len("groq/"):]
            url = "https://api.groq.com/openai/v1/chat/completions"
        elif model.startswith("mistral/"):
            model_name = model[len("mistral/"):]
            url = "https://api.mistral.ai/v1/chat/completions"
        elif model.startswith("openai/"):
            model_name = model[len("openai/"):]
            url = "https://api.openai.com/v1/chat/completions"
        else:
            # 默认当 OpenAI 兼容
            model_name = model
            url = "https://api.openai.com/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        return url, "openai_compat", headers, model_name

    def _build_messages(self, history, user_input, registry=None, tools=None, image_parts=None):
        messages = []
        system = self.system_prompt or ""

        # Skill 创建路径规则：始终注入，确保 agent 写入正确目录
        system += (
            "\n\n## Skill 创建规则（必须遵守）\n"
            "- 创建新 skill 时，**必须**写入目录：`backend/Symbix_sdk/skill/installed_skill/<skill-name>/`\n"
            "- **优先使用 `create_skill` 工具**生成完整骨架（SKILL.md + agents/scripts/references/assets），"
            "不要在其他路径手动建目录\n"
            "- skill 名称使用英文小写 + 连字符（如 `pdf-helper`）；"
            "`description` 写 WHAT + WHEN，第三人称\n"
            "- 创建后可用 `skill__<name>` 工具加载该 skill 的完整说明；"
            "也可调用 `/skills/reload` 热加载\n"
            "- 禁止把 skill 写到项目根目录、临时目录或其他无关路径"
        )

        if registry:
            skill_overview = registry.inject_skill_overview()
            system += skill_overview
            skill_injection = registry.inject_relevant(user_input)
            if skill_injection:
                system += "\n\n[匹配到的技能指南]\n"
                system += skill_injection

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
        if image_parts:
            content_parts = [{"type": "text", "text": user_input or ""}]
            for part in image_parts:
                if not isinstance(part, dict):
                    continue
                # 已是 OpenAI 格式
                if part.get("type") == "image_url":
                    content_parts.append(part)
                    continue
                # file_pipeline 原始格式 {mime, base64, filename}
                b64 = part.get("base64") or ""
                mime = part.get("mime") or "image/png"
                if b64:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    })
            if len(content_parts) == 1:
                messages.append({"role": "user", "content": user_input or ""})
            else:
                messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user_input})
        return messages

    # ── 非流式（保留 litellm，用于非流式场景）────────────────
    def _prepare_litellm_endpoint(
        self,
        raw_model: str,
        raw_base: Optional[str],
    ) -> tuple[str, Optional[str], Optional[str]]:
        """为 litellm 准备 (model, api_base, custom_llm_provider)。

        注意：不能直接解包 _resolve_endpoint——它返回的是
        (url, provider_type, headers, model_name)，字段语义不同。
        """
        if raw_base:
            api_base_val = raw_base.rstrip("/")
            # 自动补齐 /v1（与 _resolve_endpoint 行为一致）
            if not api_base_val.endswith("/v1"):
                api_base_val = api_base_val + "/v1"
            # 自定义/中转走 OpenAI 兼容协议
            if raw_model.startswith("openai/"):
                model = raw_model[len("openai/"):]
            else:
                model = raw_model
            return model, api_base_val, "openai"

        # 无自定义 base：交给 litellm 按 model 前缀路由
        return raw_model, None, None

    async def chat(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
        registry=None,
        override_api_key: str = None,
        override_api_base: str = None,
        override_model: str = None,
        image_parts: Optional[list[dict]] = None,
    ) -> dict:
        import litellm
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        model, api_base_val, custom_provider = self._prepare_litellm_endpoint(
            raw_model, raw_base
        )

        api_key_val = override_api_key or provider.api_key
        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools, image_parts=image_parts)

        kwargs = {"model": model, "messages": messages}
        if api_key_val:
            kwargs["api_key"] = api_key_val
        if api_base_val:
            kwargs["api_base"] = api_base_val
        if custom_provider:
            kwargs["custom_llm_provider"] = custom_provider
        if tools:
            kwargs["tools"] = tools

        print(">>> [chat] model:", model, "api_base:", api_base_val)
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "reasoning": getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None),
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
        image_parts: Optional[list[dict]] = None,
    ) -> dict:
        import litellm
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        model, api_base_val, custom_provider = self._prepare_litellm_endpoint(
            raw_model, raw_base
        )

        api_key_val = override_api_key or provider.api_key
        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools, image_parts=image_parts)
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": tr["tool_call_id"], "type": "function",
                 "function": {"name": tr["name"], "arguments": tr.get("arguments", "{}") or "{}"}}
                for tr in (tool_results or [])
            ],
        })
        for tr in (tool_results or []):
            messages.append({
                "role": "tool",
                "tool_call_id": tr["tool_call_id"],
                "name": tr["name"],
                "content": tr["content"],
            })

        kwargs = {"model": model, "messages": messages}
        if api_key_val:
            kwargs["api_key"] = api_key_val
        if api_base_val:
            kwargs["api_base"] = api_base_val
        if custom_provider:
            kwargs["custom_llm_provider"] = custom_provider
        if tools:
            kwargs["tools"] = tools

        print(">>> [tool_results] model:", model)
        response = await litellm.acompletion(**kwargs)
        message = response.choices[0].message
        return {
            "content": message.content,
            "reasoning": getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None),
            "tool_calls": message.tool_calls,
            "model": response.model,
        }

    # ── 原生 HTTP 流式 SSE ────────────────────────────────────
    async def chat_stream(
        self,
        user_input: str,
        history: list[dict] = None,
        tools: Optional[list[dict]] = None,
        registry=None,
        override_api_key: str = None,
        override_api_base: str = None,
        override_model: str = None,
        image_parts: Optional[list[dict]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        流式输出统一的 dict 事件，绕过 litellm：
        - {"type":"delta","content":"..."}
        - {"type":"reasoning","content":"..."}
        - {"type":"tool_call","id":"call_xx","name":"fn","arguments":"分片..."}
        - {"type":"done","content":"完整文本","tool_calls":[...]}
        """
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        api_key = override_api_key or provider.api_key

        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools, image_parts=image_parts)

        url, provider_type, headers, model_name = self._resolve_endpoint(raw_model, raw_base, api_key)
        print(f"[stream] {provider_type} → {url}, model={model_name}")

        if provider_type == "anthropic":
            async for event in self._stream_anthropic(url, headers, model_name, messages, tools):
                yield event
        elif provider_type == "gemini":
            async for event in self._stream_gemini(url, headers, messages, tools):
                yield event
        else:
            # openai_compat / custom_openai
            async for event in self._stream_openai_compat(url, headers, model_name, messages, tools):
                yield event

    # ── Anthropic SSE 解析 ────────────────────────────────────
    async def _stream_anthropic(
        self, url: str, headers: dict, model: str, messages: list, tools: Optional[list] = None
    ) -> AsyncGenerator[dict, None]:
        """Anthropic Messages API 原生 SSE 流"""
        body = {
            "model": model,
            "messages": [m for m in messages if m["role"] != "system"],
            "max_tokens": 4096,
            "stream": True,
        }
        # system prompt 单独字段
        sys_msg = next((m["content"] for m in messages if m["role"] == "system"), None)
        if sys_msg:
            body["system"] = sys_msg

        if tools:
            anthropic_tools = []
            for t in tools:
                if t.get("type") == "function":
                    f = t["function"]
                    anthropic_tools.append({
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "input_schema": f.get("parameters", {"type": "object", "properties": {}}),
                    })
            if anthropic_tools:
                body["tools"] = anthropic_tools

        full_text = ""
        tool_calls: list[dict] = []           # [{id, name, arguments}]
        current_tool_id = None
        current_tool_name = None
        current_tool_args = ""
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    print(f"[Anthropic] HTTP {resp.status_code}: {error_text.decode()[:500]}")
                    yield {"type": "delta", "content": f"[错误] HTTP {resp.status_code}"}
                    yield {"type": "done", "content": ""}
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        evt = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    evt_type = evt.get("type", "")
                    if evt_type == "message_start":
                        continue
                    elif evt_type == "content_block_start":
                        cb = evt.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            current_tool_id = cb.get("id", "")
                            current_tool_name = cb.get("name", "")
                            current_tool_args = ""
                    elif evt_type == "content_block_delta":
                        delta = evt.get("delta", {})
                        d_type = delta.get("type", "")
                        if d_type == "text_delta":
                            text_chunk = delta.get("text", "")
                            full_text += text_chunk
                            yield {"type": "delta", "content": text_chunk}
                        elif d_type == "input_json_delta":
                            partial = delta.get("partial_json", "")
                            current_tool_args += partial
                            yield {"type": "tool_call", "id": current_tool_id, "name": current_tool_name, "arguments": partial}
                    elif evt_type == "content_block_stop":
                        # 工具调用参数累积完毕
                        if current_tool_id and current_tool_name:
                            try:
                                parsed_args = json.loads(current_tool_args)
                                formatted_args = json.dumps(parsed_args, ensure_ascii=False)
                            except json.JSONDecodeError:
                                formatted_args = current_tool_args
                            tool_calls.append({
                                "id": current_tool_id,
                                "name": current_tool_name,
                                "arguments": formatted_args,
                            })
                            current_tool_id = None
                            current_tool_name = None
                            current_tool_args = ""
                    elif evt_type == "message_delta":
                        pass
                    elif evt_type == "message_stop":
                        break

        yield {
            "type": "done",
            "content": full_text,
            "tool_calls": tool_calls if tool_calls else None,
        }

    # ── OpenAI 兼容 SSE 解析 ──────────────────────────────────
    async def _stream_openai_compat(
        self, url: str, headers: dict, model: str, messages: list, tools: Optional[list] = None
    ) -> AsyncGenerator[dict, None]:
        """OpenAI /v1/chat/completions 及兼容接口 SSE 流"""
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            clean_tools = _sanitize_tools(tools)
            if clean_tools:
                body["tools"] = clean_tools
                body["tool_choice"] = "auto"

        full_text = ""
        full_reasoning = ""
        tool_calls_acc: dict[int, dict] = {}   # index → {id, name, arguments}

        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    print(f"[OpenAI] HTTP {resp.status_code}: {error_text.decode()[:500]}")
                    yield {"type": "delta", "content": f"[错误] HTTP {resp.status_code}"}
                    yield {"type": "done", "content": ""}
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        evt = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    choices = evt.get("choices", [])
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta", {})

                    # 文本增量
                    content = delta.get("content")
                    if content:
                        full_text += content
                        yield {"type": "delta", "content": content}

                    # 推理增量（DeepSeek / Groq thinking）
                    reasoning_chunk = delta.get("reasoning_content")
                    if reasoning_chunk:
                        full_reasoning += reasoning_chunk
                        yield {"type": "reasoning", "content": reasoning_chunk}

                    # 工具调用增量
                    tc_deltas = delta.get("tool_calls")
                    if tc_deltas:
                        for tc in tc_deltas:
                            idx = tc.get("index", 0)
                            if idx not in tool_calls_acc:
                                tool_calls_acc[idx] = {"id": "", "name": "", "arguments": ""}
                            entry = tool_calls_acc[idx]
                            if tc.get("id"):
                                entry["id"] = tc["id"]
                            func = tc.get("function", {})
                            if func.get("name"):
                                entry["name"] = func["name"]
                            if func.get("arguments"):
                                entry["arguments"] += func["arguments"]
                                yield {"type": "tool_call", "id": entry["id"], "name": entry["name"], "arguments": func["arguments"]}

        tool_calls = [
            {"id": e["id"], "name": e["name"], "arguments": e["arguments"]}
            for e in tool_calls_acc.values() if e["id"]
        ]

        yield {
            "type": "done",
            "content": full_text,
            "reasoning": full_reasoning if full_reasoning else None,
            "tool_calls": tool_calls if tool_calls else None,
        }

    # ── Gemini SSE 解析 ───────────────────────────────────────
    async def _stream_gemini(
        self, url: str, headers: dict, messages: list, tools: Optional[list] = None
    ) -> AsyncGenerator[dict, None]:
        """Gemini API SSE 流"""
        # 转换 messages 格式
        contents = []
        sys_prompt = ""
        for m in messages:
            if m["role"] == "system":
                sys_prompt = m["content"]
            elif m["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": m["content"]}]})
            elif m["role"] == "assistant":
                parts = [{"text": m["content"]}] if m["content"] else []
                contents.append({"role": "model", "parts": parts})

        body = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
            },
        }
        if sys_prompt:
            body["systemInstruction"] = {"parts": [{"text": sys_prompt}]}
        if tools:
            gemini_tools = []
            for t in tools:
                if t.get("type") == "function":
                    f = t["function"]
                    gemini_tools.append({"functionDeclarations": [{
                        "name": f["name"],
                        "description": f.get("description", ""),
                        "parameters": f.get("parameters", {"type": "OBJECT", "properties": {}}),
                    }]})
            if gemini_tools:
                body["tools"] = gemini_tools

        full_text = ""
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("POST", url, headers=headers, json=body) as resp:
                if resp.status_code != 200:
                    error_text = await resp.aread()
                    print(f"[Gemini] HTTP {resp.status_code}: {error_text.decode()[:500]}")
                    yield {"type": "delta", "content": f"[错误] HTTP {resp.status_code}"}
                    yield {"type": "done", "content": ""}
                    return

                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    try:
                        evt = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    candidates = evt.get("candidates", [])
                    if not candidates:
                        continue
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    for part in parts:
                        text = part.get("text", "")
                        if text:
                            full_text += text
                            yield {"type": "delta", "content": text}

        yield {
            "type": "done",
            "content": full_text,
            "tool_calls": None,
        }