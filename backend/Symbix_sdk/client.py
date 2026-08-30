import json
import asyncio
import httpx
from typing import AsyncGenerator, Optional
from .providers import ProviderRegistry, ProviderConfig, resolve_capabilities
from .color_extract import extract_palette_b64, palette_to_hint


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
    def _resolve_endpoint(self, model: str, api_base: str, api_key: str) -> tuple[str, str, dict, str]:
        """返回 (url, provider_type, headers, model_name)。
        provider_type ∈ {'anthropic', 'gemini', 'openai_compat', 'custom_openai'}
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

        # 根据模型前缀判断（由来已久的 ``<provider>/<model>`` 命名约定）
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

        # 根据 provider 前缀路由各 OpenAI 兼容 provider。
        # 这里是需要频繁补全的表：新增 provider 时补一个 elif 即可。
        _PROVIDER_URLS = {
            "openai":   "https://api.openai.com/v1/chat/completions",
            "deepseek": "https://api.deepseek.com/v1/chat/completions",
            "groq":     "https://api.groq.com/openai/v1/chat/completions",
            "mistral":  "https://api.mistral.ai/v1/chat/completions",
            "moonshot": "https://api.moonshot.cn/v1/chat/completions",  # Kimi
            "xai":      "https://api.x.ai/v1/chat/completions",          # Grok
            # 通灵千问 / 阿里云百川通过 DashScope 提供 OpenAI 兼容接口
            "qwen":     "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            # 智谱 GLM 通过 open.bigmodel 提供 OpenAI 兼容接口
            "zhipu":    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            # OpenRouter 作为统一中转
            "openrouter": "https://openrouter.ai/api/v1/chat/completions",
            # Together / Fireworks / Anyscale 等可同此补充
            "together":  "https://api.together.xyz/v1/chat/completions",
            "fireworks": "https://api.fireworks.ai/inference/v1/chat/completions",
            # Ollama 本地推理（默认 11434，可由 providers.json api_base 覆盖）
            "ollama":    "http://localhost:11434/v1/chat/completions",
        }
        prefix = None
        model_name = model
        for p in _PROVIDER_URLS.keys():
            if model.startswith(p + "/"):
                prefix = p
                model_name = model[len(p) + 1:]
                break
        if prefix is None:
            # 未知前缀：不要默认发到 openai.com、那只是制造诡异的 401。
            # 转为openai/ 路由但不期待它成功；调用方会拿到上游错误。
            # 这比“默默路由错地」安全得多。
            raise RuntimeError(
                f"未知 provider 前缀: {model!r}。请在 backend/Symbix_sdk/client.py "
                f"_PROVIDER_URLS 里补上対应的 OpenAI 兼容接口 URL，"
                f"或在 providers.json 里设 api_base 走自定义中转。"
            )
        url = _PROVIDER_URLS[prefix]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }
        return url, "openai_compat", headers, model_name

    def _build_messages(self, history, user_input, registry=None, tools=None, image_parts=None,
                         supports_vision: Optional[bool] = None):
        messages = []
        system = self.system_prompt or ""
        # 如果调用方未显式指定，则从 active provider 推断视觉能力
        if image_parts and supports_vision is None:
            try:
                p = self.registry.get_active()
                caps = resolve_capabilities(p.model, p)
                supports_vision = caps.get("supports_vision", False)
            except RuntimeError:
                supports_vision = False

        # Skill 创建路径规则：始终注入，确保 agent 写入正确目录
        system += (
            "\n\n## 工具调用循环纪律（必须遵守）\n"
            "- 每个任务最多调用同名的写入类工具（edit_file/create_skill/...) 2 次。若第二次结果变不了，不要持续重复。\n"
            "- 收到任何工具执行成功的结果后（如 `File saved:` ），下一步应直接向用户总结，不要继续重复创建/写同一批文件。\n"
            "- 禁止在同一轮对话内连续 创建/写入 不同名称但内容实质近似的文件超过 2 个；若需批量同类生成，先向用户说明并征得同意。\n"
            "- 反复调用相同或近似工具而不产生新进展算运行故障，必须停止并清晰说明已完成的实际进度、未能完成的处与原因。\n\n"
            "## Skill 创建规则（必须遵守）\n"
            "- 创建新 skill 时,**必须**写入目录:`backend/Symbix_sdk/skill/installed_skills/<skill-name>/`\n"
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
            if not supports_vision:
                # 模型不支持视觉 → 降级为文字描述,避免 multimodal payload 被 400。
                # 同时用 Pylette/Pillow 提取主色,拼进提示,让 skill LLM 生成 SVG 时颜色尽量贴合参考图。
                image_summary_parts = []
                for p in image_parts:
                    if not isinstance(p, dict):
                        continue
                    filename = p.get('filename') or p.get('mime') or 'unknown'
                    label = f"[图片: {filename}]"
                    # 尝试提取主色:失败静默,不影响降级文本
                    hexes = extract_palette_b64(p.get('base64') or '')
                    hint = palette_to_hint(hexes)
                    image_summary_parts.append(label + (f"({hint})" if hint else ""))
                image_summary = ", ".join(image_summary_parts)
                messages.append({
                    "role": "user",
                    "content": f"{user_input or ''}\n{image_summary}".strip(),
                })
                return messages
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

    # ── 非流式（原生 HTTP，复用流式管道聚合；不再依赖 litellm）────────
    def _build_tool_result_messages(self, messages: list[dict], tool_results: list[dict]) -> list[dict]:
        """把工具执行结果回传拼成 assistant tool_calls + tool 消息，供续聊使用。"""
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
        return messages

    async def _chat_raw(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        raw_model: str = None,
        raw_base: str = None,
        api_key: str = None,
        caps: Optional[dict] = None,
    ) -> dict:
        """非流式核心：解析端点 + 分发到原生流式管道，聚合结果返回。

        返回 dict：{"content", "reasoning", "tool_calls"(dict 列表 or None), "model", "error"}
        tool_calls 每项为 {"id", "name", "arguments"}（与 chat_stream 的 done 事件一致）。
        """
        url, provider_type, headers, model_name = self._resolve_endpoint(raw_model, raw_base, api_key)

        if provider_type == "anthropic":
            gen = self._stream_anthropic(url, headers, model_name, messages, tools)
        elif provider_type == "gemini":
            gen = self._stream_gemini(url, headers, messages, tools)
        else:
            gen = self._stream_openai_compat(url, headers, model_name, messages, tools, caps=caps)

        async for evt in gen:
            if evt.get("type") == "done":
                return {
                    "content": evt.get("content", ""),
                    "reasoning": evt.get("reasoning"),
                    "tool_calls": evt.get("tool_calls"),
                    "model": model_name,
                    "error": evt.get("error"),
                }
        # 流意外结束（无 done 事件）时兜底
        return {"content": "", "reasoning": None, "tool_calls": None, "model": model_name}

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
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        api_key_val = override_api_key or provider.api_key

        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools, image_parts=image_parts)
        caps = resolve_capabilities(raw_model, provider)
        # 不支持视觉模型时，主动降级为纯文本（防止 multimodal 端点 400）。
        if image_parts and not caps.get("supports_vision"):
            for m in messages:
                if isinstance(m.get("content"), list):
                    m["content"] = "".join(
                        p.get("text", "") for p in m["content"] if p.get("type") == "text"
                    ) or "[user message]"

        print(">>> [chat] model:", raw_model, "base:", raw_base, "caps:", caps)
        return await self._chat_raw(messages, tools, raw_model, raw_base, api_key_val, caps)

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
        provider = self.registry.get_active()
        raw_model = override_model or provider.model
        raw_base = override_api_base or provider.api_base
        api_key_val = override_api_key or provider.api_key

        messages = self._build_messages(history or [], user_input, registry=registry, tools=tools, image_parts=image_parts)
        messages = self._build_tool_result_messages(messages, tool_results)
        caps = resolve_capabilities(raw_model, provider)

        print(">>> [tool_results] model:", raw_model, "caps:", caps)
        return await self._chat_raw(messages, tools, raw_model, raw_base, api_key_val, caps)

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
        流式输出统一的 dict 事件（原生 HTTP，不经过 litellm）:
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
        self, url: str, headers: dict, model: str, messages: list,
        tools: Optional[list] = None, max_retries: int = 2,
        caps: Optional[dict] = None,
        caps_model_override: Optional[str] = None,
    ) -> AsyncGenerator[dict, None]:
        """OpenAI /v1/chat/completions 及兼容接口 SSE 流（带断线重试）。

        caps 来自 provider capability 解析，优先级：显式 caps > caps_model_override 推断 > active provider。
        chat_stream 调用时务必传 caps_model_override=raw_model（带前缀）,
        以避免在 active provider 与本次请求 model 不一致时拿错能力位
        （典型场景：前端选 z-ai/glm-5.2，但 providers.json active.model 是
        gemini-3-flash-preview，旧路径会让 active 的 openai 默认能力位生效,
        错误把 prompt_cache_key 塞进 body 导致上游 400 Unsupported parameter）。
        """
        # 能力位解析（让上游 422 的可能性尽可能低）
        if caps is None:
            try:
                p = self.registry.get_active()
                # 优先用 caps_model_override 推断（带前缀更准），active provider 仅作 fallback。
                infer_model = caps_model_override or p.model
                caps = resolve_capabilities(infer_model, p)
            except RuntimeError:
                caps = dict(supports_tools=True, supports_prompt_cache=False,
                            supports_vision=False, supports_reasoning=False,
                            supports_streaming=True, api_kind="openai_compat")

        body = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        # 仅在 provider 支持工具时才下发。
        if tools and caps.get("supports_tools", True):
            clean_tools = _sanitize_tools(tools)
            if clean_tools:
                body["tools"] = clean_tools
                body["tool_choice"] = "auto"
        # 提示缓存：OpenAI / DeepSeek 都支持 prompt_cache_key 来重启前缀缓存
        if caps.get("supports_prompt_cache"):
            body["prompt_cache_key"] = "symbix-session"

        # 分开设置各阶段超时，而不是一个数字打天下
        timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

        for attempt in range(max_retries + 1):
            full_text = ""
            full_reasoning = ""
            tool_calls_acc: dict[int, dict] = {}   # index → {id, name, arguments}

            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
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

                # 正常读完整个流，直接 done 并退出（不再继续重试循环）
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
                return

            except (httpx.RemoteProtocolError, httpx.ReadError,
                    httpx.ReadTimeout, httpx.ConnectError) as e:
                print(f"[OpenAI] 流式连接第 {attempt + 1} 次中断: {e}")
                if attempt < max_retries:
                    # 已吐给前端的这部分内容作废，通知前端清空后重新开始
                    yield {"type": "stream_reset", "reason": str(e), "attempt": attempt + 1}
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    # 重试次数用尽，把已生成内容也带出去，标记为不完整
                    yield {
                        "type": "done",
                        "content": full_text or "",
                        "reasoning": full_reasoning or None,
                        "tool_calls": None,
                        "error": f"连接多次中断（{e}），内容可能不完整",
                    }
                    return

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