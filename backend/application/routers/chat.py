"""对话相关路由：/chat, /chat/stream, /chat/approve, /upload, /parse_file, /history"""
import asyncio
import uuid
import json as _json
import httpx
from fastapi import APIRouter, HTTPException, File, UploadFile, Form, Request
from fastapi.responses import StreamingResponse

from application.schemas import ChatRequest, ChatResponse, ApproveRequest
from application.state import (
    memory,
    provider_registry,
    skill_registry,
    symbix_client,
    act_mode_controller,
    tool_registry,
    APPROVAL_TOOLS,
    _pending_approvals,
    _processing_approvals,
)
from Symbix_sdk.tools.risk_classifier import classify_tool_risk, ToolRiskLevel
from Symbix_sdk.model_capabilities import check_vision, clear_vision_cache
from application.services.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
    build_system_prompt,
)

router = APIRouter(tags=["chat"])


# 为避免上游 模型逐 token 推 delta 导致前端 高频解析/rAF 重绘，这里将连续 delta 事件批量合并
class _DeltaBatcher:
    """攒批 delta 事件：相邻 delta 合并到默认 彈；遇非 delta 或达上限立即 flush。"""
    def __init__(self, max_chunks: int = 1, max_chars: int = 8) -> None:
        # 阈值已降至近实时转发（来一个 delta 即 flush），
        # 仅保留结构以备极端高频场景下做轻度节流。
        self.max_chunks = max_chunks
        self.max_chars = max_chars
        self._buf = ""
        self._n = 0
        self._has = False

    def add_delta(self, s: str) -> dict | None:
        """加入 delta，返回 flush 事件（若需）或 None仍需继续攒。"""
        if not s:
            return None
        self._buf += s
        self._n += 1
        self._has = True
        if self._n >= self.max_chunks or len(self._buf) >= self.max_chars:
            return self.flush()
        return None

    def flush(self) -> dict | None:
        if not self._has:
            return None
        evt = {"type": "delta", "content": self._buf}
        self._buf = ""
        self._n = 0
        self._has = False
        return evt


def _batch_yield(
    event: dict,
    batcher: "_DeltaBatcher",
    on_delta: "callable[[str], None] | None" = None,
):
    """对单个上游事件，返回需 yield 的 SSE 字符串列表（顺序：先 flush缓冲 delta，再透传本事件）。"""
    out: list[str] = []
    etype = event.get("type")
    if etype == "delta":
        content = event.get("content", "")
        if on_delta is not None:
            on_delta(content)
        flushed = batcher.add_delta(content)
        if flushed is not None:
            out.append(format_sse(flushed))
        return out
    # 非 delta：先 flush 缓冲，再透传
    flushed = batcher.flush()
    if flushed is not None:
        out.append(format_sse(flushed))
    out.append(format_sse(event))
    return out


# ═══════════════ Checkpoint 记录辅助 ═══════════════
# 在 chat_stream / chat / approve 三处调用,把工具调用 + round 总结点写进 sqlite。
# 继续 fire-and-forget 语义——写 checkpoint 不能阻断主业务流。
from application.state import checkpoint_recorder  # noqa: E402


def _new_round_id() -> str:
    """生成一轮 user_msg → agent 的 round 标识。"""
    return uuid.uuid4().hex[:12]


def _emit_tool(
    session_id: str,
    round_id: str,
    tc_name: str,
    tc_args,
    risk_level,
    approved: bool,
    tool_output: str,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """统一处理 tool_call 的 checkpoint 发射。】"""
    try:
        args_dict = (
            _json.loads(tc_args) if isinstance(tc_args, str) and tc_args else
            (tc_args if isinstance(tc_args, dict) else {})
        )
    except Exception:
        args_dict = {"_raw": str(tc_args)}
    # risk_level 可能是 ToolRiskLevel 枚举或 str
    rl = str(risk_level).split(".")[-1].lower() if risk_level else "unknown"
    try:
        checkpoint_recorder.emit_tool_call(
            session_id=session_id,
            round_id=round_id,
            tool_name=tc_name,
            arguments=args_dict,
            risk_level=rl,
            approved=approved,
            status=status,
            error=error,
            result_snippet=tool_output or "",
        )
    except Exception as e:
        print(f"[checkpoint] emit_tool_call failed: {e}")


def _emit_round_summary(
    session_id: str,
    round_id: str,
    user_msg: str,
    assistant_text: str,
    reasoning: str | None,
    tool_count: int,
    failed_tools: int,
    duration_ms: int = 0,
) -> None:
    """一轮结束时发送 round 总结点。"""
    try:
        checkpoint_recorder.emit_round(
            session_id=session_id,
            round_id=round_id,
            user_msg=user_msg or "",
            assistant_text=assistant_text or "",
            reasoning=reasoning or "",
            tool_count=tool_count,
            failed_tools=failed_tools,
            duration_ms=duration_ms,
        )
    except Exception as e:
        print(f"[checkpoint] emit_round failed: {e}")


def _prepare_user_message(
    request: ChatRequest,
) -> tuple[str, list[dict], list[dict]]:
    """
    解析 attachments 并注入用户消息；返回 (enriched_text, parsed_list, image_parts)。

    注意：本函数不做视觉能力检测，始终返回 image_parts。
    视觉能力检测是异步操作，需在调用点用 check_vision() 完成。
    """
    from Symbix_sdk.tools.file_pipeline import inject_attachments_into_message

    atts = []
    for a in request.attachments or []:
        if hasattr(a, "model_dump"):
            atts.append(a.model_dump())
        elif isinstance(a, dict):
            atts.append(a)
        else:
            atts.append(dict(a))

    enriched, parsed_list, image_parts = inject_attachments_into_message(
        request.message, atts
    )
    return enriched, parsed_list, image_parts


async def _filter_image_parts(
    image_parts: list[dict],
    model: str,
    api_key: str,
    api_base: str,
) -> list[dict]:
    """
    根据模型视觉能力过滤 image_parts。
    有图片且模型不支持视觉时，异步探测并降级为空列表。
    """
    if not image_parts:
        return image_parts
    supports = await check_vision(model, api_key, api_base)
    if not supports:
        print(f"[chat] 模型 {model} 不支持视觉，{len(image_parts)} 张图片降级为文本描述")
        return []
    return image_parts


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    session_id: str = Form("default"),
):
    """上传一个或多个附件到 uploads/{session_id}/。"""
    from Symbix_sdk.tools.file_pipeline import save_upload, parse_file_path

    results = []
    for uf in files:
        data = await uf.read()
        meta = save_upload(
            session_id=session_id or "default",
            filename=uf.filename or "file",
            data=data,
        )
        if meta.get("status") == "ok":
            preview = parse_file_path(
                meta["path"],
                max_chars=2000,
                include_image_base64=False,
            )
            meta["kind"] = preview.get("kind")
            meta["preview"] = (preview.get("text") or "")[:500]
        results.append(meta)

    ok_count = sum(1 for r in results if r.get("status") == "ok")
    return {
        "status": "ok" if ok_count else "error",
        "uploaded": results,
        "count": ok_count,
    }


@router.post("/parse_file")
async def parse_file_api(body: dict):
    """按路径解析已上传/工作区内文件。"""
    from Symbix_sdk.tools.file_pipeline import parse_file_path

    path = (body or {}).get("path") or (body or {}).get("file_path") or ""
    max_chars = int((body or {}).get("max_chars") or 50000)
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    return parse_file_path(path, max_chars=max_chars, include_image_base64=False)


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    try:
        api_key = request.api_key or provider_registry.get_active().api_key
        api_base = request.api_base or provider_registry.get_active().api_base
        model = request.model or provider_registry.get_active().model

        user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
        # 有图片时，异步探测模型视觉能力并按需降级
        image_parts = await _filter_image_parts(image_parts, model, api_key, api_base)
        mem_msg = request.message
        if request.attachments:
            names = [
                (a.filename or a.name or a.path or "file")
                for a in request.attachments
            ]
            mem_msg = (mem_msg + "\n" if mem_msg else "") + " ".join(
                f"[文件: {n}]" for n in names
            )
        memory.add(request.session_id, "user", mem_msg)
        history = memory.get_compressed_history(request.session_id, recent_limit=20)
        act_decision = act_mode_controller.decide(mem_msg, history[:-1])
        act_mode = act_decision.judgment.mode.value
        act_plan = act_decision.plan

        # 注入 RAG 记忆到 system prompt
        use_mem = getattr(request, "use_memory", True)
        enriched_prompt = build_system_prompt(
            base=request.system_prompt,
            use_memory=use_mem,
            user_query=mem_msg,
            session_id=request.session_id,
        )
        if act_mode == "reactive":
            enriched_prompt += (
                "\n\n[Act Mode: reactive]\n"
                "直接回应当前请求,保持简洁;如果需要工具,先判断必要性再行动。"
            )
        else:
            plan_text = "\n".join(f"{i}. {step}" for i, step in enumerate(act_plan, 1))
            enriched_prompt += (
                "\n\n[Act Mode: plan_solve]\n"
                "请遵循以下行为计划,并在工具结果后继续检查和调整:\n"
                f"{plan_text}\n"
                "完成后进行简短反思,确认是否满足用户原始目标。"
            )
        symbix_client.system_prompt = enriched_prompt

        # native 工具（含 emit_pet_action / 文件 / skill）始终可用；
        # use_mcp 仅控制是否附带外部 MCP 工具
        if request.use_mcp:
            mcp_tools = tool_registry.get_openai_tools()
        else:
            mcp_tools = tool_registry.native.get_openai_tools()


        steps = []
        last_reasoning = None

        response = await symbix_client.chat(
            user_input=user_for_llm,
            history=history[:-1],
            registry=skill_registry,
            tools=mcp_tools,
            override_api_key=api_key,
            override_api_base=api_base,
            override_model=model,
            image_parts=image_parts or None,
        )

        last_reasoning = response.get("reasoning")

        # checkpoint：本轮 user_msg → agent 标识
        ckpt_round_id = _new_round_id()
        ckpt_tool_count = 0
        ckpt_failed = 0
        ckpt_start_ts = asyncio.get_event_loop().time()

        max_tool_rounds = 25
        round_count = 0
        nonstream_name_counts: dict[str, int] = {}
        NONSTREAM_WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                                 "delete_file", "create_skill", "run_command",
                                 "open_terminal"}
        MAX_NS_WRITE = 3

        while response.get("tool_calls") and round_count < max_tool_rounds:
            # 客户端断连检测：前端 abort / 删 session 会断 SSE 连接。当前是 /chat（非 SSE）路径，但仍终止以免堆跑无效 tool_calls。
            if await http_request.is_disconnected():
                break
            round_count += 1
            tool_results = []

            steps.append({
                "type": "tool_calls",
                "reasoning": response.get("reasoning"),
                "tool_calls": [
                    {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                    for tc in response["tool_calls"]
                ],
            })

            for tc in response["tool_calls"]:
                fn = tc.function
                # 解析参数用于风险分级
                try:
                    args = _json.loads(fn.arguments) if isinstance(fn.arguments, str) else fn.arguments
                except Exception:
                    args = {}

                # 频次反循环：多次同一写入工具 → 直接跳出循环并记录停止原因
                if fn.name in NONSTREAM_WRITE_TOOLS:
                    nonstream_name_counts[fn.name] = nonstream_name_counts.get(fn.name, 0) + 1
                    if nonstream_name_counts[fn.name] > MAX_NS_WRITE:
                        stop_hint = (
                            f"[System] 工具 `{fn.name}` 已被调用 "
                            f"{nonstream_name_counts[fn.name] - 1} 次。"
                            "请停止重复调用，直接向用户总结已完成的工作与原因，不要继续调用任何写入类工具。"
                        )
                        tool_results.append({
                            "tool_call_id": tc.id,
                            "role": "tool",
                            "name": fn.name,
                            "content": stop_hint,
                            "arguments": fn.arguments,
                        })
                        steps.append({
                            "type": "tool_result",
                            "tool_call_id": tc.id,
                            "name": fn.name,
                            "content": stop_hint,
                        })
                        # 强制跳出 while 循环
                        response = {"content": stop_hint, "tool_calls": None, "reasoning": last_reasoning}
                        break

                # 使用风险分级器判断是否需要审批
                risk_level, risk_reason = classify_tool_risk(fn.name, args)
                
                # SAFE 工具直接放行，MEDIUM/HIGH 需要审批
                if risk_level != ToolRiskLevel.SAFE:
                    approval_id = str(uuid.uuid4())
                    _pending_approvals[approval_id] = {
                        "session_id": request.session_id,
                        "user_input": user_for_llm,
                        "history": history[:-1],
                        "mcp_tools": mcp_tools,
                        "api_key": api_key,
                        "api_base": api_base,
                        "model": model,
                        "steps": steps,
                        "last_reasoning": last_reasoning,
                        "round_count": round_count,
                        "act_mode": act_mode,
                        "act_plan": act_plan,
                        "pending_tc": {"id": tc.id, "name": fn.name, "arguments": fn.arguments},
                        "ckpt_round_id": ckpt_round_id,
                        "remaining_tcs": [
                            {"id": r.id, "name": r.function.name, "arguments": r.function.arguments}
                            for r in response["tool_calls"]
                        ],
                        "risk_level": risk_level,
                        "risk_reason": risk_reason,
                    }

                    # — checkpoint: 需审批工具被拦 → 记 skipped + round 未完待续
                    ckpt_tool_count += 1
                    _emit_tool(request.session_id, ckpt_round_id, fn.name, fn.arguments,
                               risk_level, False, "", status="skipped",
                               error="awaiting user approval")
                    _emit_round_summary(
                        request.session_id, ckpt_round_id,
                        mem_msg, "", last_reasoning,
                        ckpt_tool_count, ckpt_failed,
                        duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                    )
                    return {
                        "status": "pending_approval",
                        "approval_id": approval_id,
                        "session_id": request.session_id,
                        "content": "",
                        "reasoning": last_reasoning,
                        "steps": steps,
                        "act_mode": act_mode,
                        "act_plan": act_plan,
                        "risk_level": risk_level,
                        "risk_reason": risk_reason,
                        "pending_tool": {
                            "tool_call_id": tc.id,
                            "name": fn.name,
                            "arguments": fn.arguments,
                        },
                    }

                tool_output = tool_registry.execute(fn.name, fn.arguments)
                if not isinstance(tool_output, str):
                    tool_output = _json.dumps(tool_output, ensure_ascii=False)
                tool_results.append({
                    "tool_call_id": tc.id,
                    "role": "tool",
                    "name": fn.name,
                    "content": tool_output,
                    "arguments": fn.arguments if hasattr(fn, "arguments") else "{}",
                })
                steps.append({
                    "type": "tool_result",
                    "tool_call_id": tc.id,
                    "name": fn.name,
                    "content": tool_output,
                })
                print(f"[MCP Tool] {fn.name} -> {tool_output[:200]}")
                # — checkpoint: 记一条工具调用 (非流 /chat 路径)
                ckpt_tool_count += 1
                if isinstance(tool_output, str) and tool_output.startswith("[Error"):
                    ckpt_failed += 1
                    _emit_tool(request.session_id, ckpt_round_id, fn.name, fn.arguments,
                               risk_level, True, tool_output,
                               status="error", error=tool_output[:200])
                else:
                    _emit_tool(request.session_id, ckpt_round_id, fn.name, fn.arguments,
                               risk_level, True, tool_output)

            response = await symbix_client.chat_with_tool_results(
                user_input=user_for_llm,
                history=history[:-1],
                registry=skill_registry,
                tools=mcp_tools,
                tool_results=tool_results,
                override_api_key=api_key,
                override_api_base=api_base,
                override_model=model,
                image_parts=image_parts or None,
            )
            last_reasoning = response.get("reasoning")

        assistant_content = response["content"]
        memory.add(request.session_id, "assistant", assistant_content)
        # — checkpoint: /chat (非流) 本轮完成 → 记 round 总结点
        _emit_round_summary(
            request.session_id, ckpt_round_id,
            mem_msg, assistant_content, last_reasoning,
            ckpt_tool_count, ckpt_failed,
            duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
        )

        asyncio.create_task(maybe_compress_session(
            request.session_id, api_key, api_base, model))
        asyncio.create_task(maybe_extract_memories(
            request.session_id, api_key, api_base, model))

        return ChatResponse(
            content=assistant_content,
            session_id=request.session_id,
            reasoning=last_reasoning,
            steps=steps,
            act_mode=act_mode,
            act_plan=act_plan,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/approve")
async def chat_approve(req: ApproveRequest, http_request: Request):
    print(f"[APPROVE] Received approval_id={req.approval_id}, pending keys={list(_pending_approvals.keys())}")
    if req.approval_id in _processing_approvals:
        print(f"[APPROVE] approval_id {req.approval_id} is already processing")
        raise HTTPException(status_code=409, detail="approval is already being processed")
    ctx = _pending_approvals.pop(req.approval_id, None)
    if req.system_prompt:
        symbix_client.system_prompt = req.system_prompt
    if not ctx:
        print(f"[APPROVE] approval_id {req.approval_id} not found in pending")
        raise HTTPException(status_code=404, detail="approval not found")

    # pop 后立即加锁,覆盖工具执行与后续模型生成期间的整个窗口。
    # 必须在第一个 await 之前完成,才能防止并发重复审批。
    _processing_approvals.add(req.approval_id)

    steps = ctx["steps"]
    user_input = ctx["user_input"]
    history = ctx["history"]
    mcp_tools = ctx["mcp_tools"]
    api_key = ctx["api_key"]
    api_base = ctx["api_base"]
    model = ctx["model"]
    round_count = ctx["round_count"]
    act_mode = ctx.get("act_mode", "reactive")
    act_plan = ctx.get("act_plan", [])
    pending_tc = ctx["pending_tc"]
    # checkpoint：复用原轮 ckpt_round_id，使 approve 收尾后的 round 总结继续在同一 round 内
    ckpt_round_id = ctx.get("ckpt_round_id", _new_round_id())
    ckpt_tool_count = 0
    ckpt_failed = 0
    ckpt_start_ts = asyncio.get_event_loop().time()
    remaining_tcs = ctx["remaining_tcs"]

    tool_results = []
    try:
        if req.approve:
            out = tool_registry.execute(pending_tc["name"], pending_tc["arguments"])
            if not isinstance(out, str):
                out = _json.dumps(out, ensure_ascii=False)
            steps.append({
                "type": "tool_result",
                "tool_call_id": pending_tc["id"],
                "name": pending_tc["name"],
                "content": out,
                "approved": True,
            })
            # — checkpoint: 审批同意 → 记一条 approved=True 工具调用
            ckpt_tool_count += 1
            if isinstance(out, str) and out.startswith("[Error"):
                ckpt_failed += 1
                _emit_tool(request.session_id, ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
                           ctx.get("risk_level", "medium"), True, out,
                           status="error", error=out[:200])
            else:
                _emit_tool(request.session_id, ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
                           ctx.get("risk_level", "medium"), True, out)
        else:
            out = f"[用户拒绝执行工具 {pending_tc['name']}]"
            steps.append({
                "type": "tool_result",
                "tool_call_id": pending_tc["id"],
                "name": pending_tc["name"],
                "content": out,
                "approved": False,
            })
            # — checkpoint: 用户拒绝 → 记 skipped (approved=False)
            ckpt_tool_count += 1
            _emit_tool(request.session_id, ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
                       ctx.get("risk_level", "medium"), False, "", status="skipped",
                       error="user rejected")
        tool_results.append({
            "tool_call_id": pending_tc["id"],
            "role": "tool",
            "name": pending_tc["name"],
            "content": out,
            "arguments": pending_tc["arguments"],
        })

        for tc in remaining_tcs:
            if tc["id"] == pending_tc["id"]:
                continue
            # 使用风险分级器判断剩余工具是否需要审批
            try:
                args = _json.loads(tc["arguments"]) if isinstance(tc["arguments"], str) else tc["arguments"]
            except Exception:
                args = {}
            
            risk_level, _ = classify_tool_risk(tc["name"], args)
            if risk_level != ToolRiskLevel.SAFE:
                # 如果剩余的 tool_calls 中也有需要审批的工具，应该阻挡
                r_out = f"[安全策略] 本轮还包含审批工具 '{tc['name']}'，但一次只能审批一个。请单独确认后再继续。"
            else:
                r_out = tool_registry.execute(tc["name"], tc["arguments"])
                if not isinstance(r_out, str):
                    r_out = _json.dumps(r_out, ensure_ascii=False)
            tool_results.append({
                "tool_call_id": tc["id"],
                "role": "tool",
                "name": tc["name"],
                "content": r_out,
                "arguments": tc["arguments"],
            })
            steps.append({
                "type": "tool_result",
                "tool_call_id": tc["id"],
                "name": tc["name"],
                "content": r_out,
            })

        last_reasoning = ctx.get("last_reasoning")
        max_tool_rounds = 25
        session_id = ctx["session_id"]

        # ---- 流式生成后续回复（SSE） ----
        # 审批工具已执行完，把 tool_results 作为 assistant tool_calls + tool 消息
        # 追加到 messages，然后用流式 SSE 输出，避免前端干等。
        async def _stream_approve():
            nonlocal last_reasoning
            try:
                # 先把已执行的步骤发给前端
                yield format_sse({"type": "steps", "steps": steps})

                # 构建含 tool_results 的 messages
                msgs = symbix_client._build_messages(
                    history,
                    user_input,
                    registry=skill_registry,
                    tools=mcp_tools,
                    image_parts=None,
                )
                msgs.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": tr["tool_call_id"], "type": "function",
                         "function": {"name": tr["name"], "arguments": tr.get("arguments", "{}") or "{}"}}
                        for tr in tool_results
                    ],
                })
                for tr in tool_results:
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "name": tr["name"],
                        "content": tr["content"],
                    })

                full_text = ""
                tool_calls_raw = None
                _batcher = _DeltaBatcher()

                provider = provider_registry.get_active()
                raw_model = model or provider.model
                raw_base = api_base or provider.api_base
                api_key_val = api_key or provider.api_key
                url, ptype, headers, model_name = symbix_client._resolve_endpoint(
                    raw_model, raw_base, api_key_val
                )

                # 第一轮流式输出（审批后继续生成）
                if ptype == "anthropic":
                    async for e in symbix_client._stream_anthropic(url, headers, model_name, msgs, mcp_tools):
                        if e["type"] == "stream_reset":
                            full_text = ""
                            _batcher = _DeltaBatcher()
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        for _sse in _batch_yield(e, _batcher):
                            yield _sse
                        if e["type"] == "delta":
                            full_text += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                            if e.get("error"):
                                print(f"[_stream_approve] 内容不完整: {e['error']}")
                elif ptype == "gemini":
                    async for e in symbix_client._stream_gemini(url, headers, msgs, mcp_tools):
                        if e["type"] == "stream_reset":
                            full_text = ""
                            _batcher = _DeltaBatcher()
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        for _sse in _batch_yield(e, _batcher):
                            yield _sse
                        if e["type"] == "delta":
                            full_text += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                            if e.get("error"):
                                print(f"[_stream_approve] 内容不完整: {e['error']}")
                else:
                    async for e in symbix_client._stream_openai_compat(url, headers, model_name, msgs, mcp_tools):
                        if e["type"] == "stream_reset":
                            full_text = ""
                            _batcher = _DeltaBatcher()
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        for _sse in _batch_yield(e, _batcher):
                            yield _sse
                        if e["type"] == "delta":
                            full_text += e["content"]
                        elif e["type"] == "reasoning":
                            last_reasoning = e.get("content")
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                            if e.get("reasoning"):
                                last_reasoning = e.get("reasoning")
                            if e.get("error"):
                                print(f"[_stream_approve] 内容不完整: {e['error']}")

                flushed = _batcher.flush()
                if flushed is not None:
                    yield flushed

                # 后续 tool_calls 循环（复用 chat_stream 主循环逻辑）
                round_count_local = ctx["round_count"]
                attempted = set()
                # 频次检测：同一写入类工具名不得超过 MAX_WRITE_CALLS_PER_NAME 次
                name_counts_local: dict[str, int] = {}
                LOCAL_WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                                     "delete_file", "create_skill", "run_command",
                                     "open_terminal"}
                MAX_WRITE_NAME = 3
                while tool_calls_raw and round_count_local < max_tool_rounds:
                    # 客户端断连检测：前端 abort / 删 session 会断 SSE 连接，后端需主动停。
                    if await http_request.is_disconnected():
                        print(f"[approve] client disconnected at round {round_count_local}, stopping")
                        break
                    round_count_local += 1
                    steps.append({
                        "type": "tool_calls",
                        "reasoning": last_reasoning,
                        "tool_calls": [
                            {"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                            for tc in tool_calls_raw
                        ],
                    })
                    yield format_sse({"type": "steps", "steps": steps})

                    new_results = []
                    for tc in tool_calls_raw:
                        tc_id = tc["id"]
                        tc_name = tc["name"]
                        tc_args = tc.get("arguments", "{}")

                        # 去重检测
                        try:
                            parsed = _json.loads(tc_args) if isinstance(tc_args, str) else tc_args
                            sig = (tc_name, _json.dumps(parsed, ensure_ascii=False, sort_keys=True))
                        except (TypeError, _json.JSONDecodeError):
                            sig = (tc_name, str(tc_args))
                        if sig in attempted:
                            err = f"[Error] Tool '{tc_name}' 重复调用相同参数，已阻止。"
                            steps.append({"type": "tool_result", "tool_call_id": tc_id, "name": tc_name, "content": err})
                            yield format_sse({"type": "tool_result", "id": tc_id, "name": tc_name, "content": err})
                            tool_calls_raw = None
                            full_text = full_text or err
                            break
                        attempted.add(sig)

                        # 频次检测：多次同一写入工具 → 强制终止循环，要求总结
                        if tc_name in LOCAL_WRITE_TOOLS:
                            name_counts_local[tc_name] = name_counts_local.get(tc_name, 0) + 1
                            if name_counts_local[tc_name] > MAX_WRITE_NAME:
                                stop_hint = (
                                    f"[System] 工具 `{tc_name}` 已被调用 "
                                    f"{name_counts_local[tc_name] - 1} 次。看起来你在重复/近似调用同一写入工具。"
                                    "请立即停下来，向用户总结已完成的工作，不要再调用任何写入工具。"
                                )
                                steps.append({
                                    "type": "tool_result",
                                    "tool_call_id": tc_id,
                                    "name": tc_name,
                                    "content": stop_hint,
                                })
                                yield format_sse({"type": "tool_result", "id": tc_id, "name": tc_name, "content": stop_hint})
                                tool_calls_raw = None
                                full_text = full_text or stop_hint
                                break

                        risk_level, risk_reason = classify_tool_risk(tc_name, tc_args)
                        if risk_level in (ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH):
                            approval_id = str(uuid.uuid4())
                            _pending_approvals[approval_id] = {
                                "session_id": session_id,
                                "user_input": user_input,
                                "history": history,
                                "mcp_tools": mcp_tools,
                                "api_key": api_key,
                                "api_base": api_base,
                                "model": model,
                                "steps": steps,
                                "last_reasoning": last_reasoning,
                                "round_count": round_count_local,
                                "full_text": full_text,
                                "act_mode": act_mode,
                                "act_plan": act_plan,
                                "pending_tc": {"id": tc_id, "name": tc_name, "arguments": tc_args},
                                "ckpt_round_id": ctx.get("ckpt_round_id", ckpt_round_id),
                                "remaining_tcs": [{"id": r["id"], "name": r["name"], "arguments": r.get("arguments", "{}")} for r in tool_calls_raw],
                                "risk_level": risk_level,
                                "risk_reason": risk_reason,
                            }
                            yield format_sse({
                                "type": "await_approval",
                                "approval_id": approval_id,
                                "tool": {"id": tc_id, "name": tc_name, "arguments": tc_args},
                                "risk_level": risk_level,
                                "risk_reason": risk_reason,
                                "act_mode": act_mode,
                                "act_plan": act_plan,
                            })
                            # — checkpoint: approve-stream 后续轮需审批 → 讃 skipped + 拦住本轮
                            ckpt_tool_count += 1
                            _emit_tool(session_id, ckpt_round_id, tc_name, tc_args,
                                       risk_level, False, "", status="skipped",
                                       error="awaiting user approval (nested)")
                            _emit_round_summary(
                                session_id, ckpt_round_id,
                                user_input, full_text, last_reasoning,
                                ckpt_tool_count, ckpt_failed,
                                duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                            )
                            yield format_sse({"type": "done", "content": full_text})
                            return

                        out = tool_registry.execute(tc_name, tc_args)
                        if not isinstance(out, str):
                            out = _json.dumps(out, ensure_ascii=False)
                        steps.append({"type": "tool_result", "tool_call_id": tc_id, "name": tc_name, "content": out})
                        yield format_sse({"type": "tool_result", "id": tc_id, "name": tc_name, "content": out})
                        new_results.append({"tool_call_id": tc_id, "role": "tool", "name": tc_name, "content": out, "arguments": tc_args})
                        # — checkpoint: approve-stream 后续轮工具调用
                        ckpt_tool_count += 1
                        if isinstance(out, str) and out.startswith("[Error"):
                            ckpt_failed += 1
                            _emit_tool(session_id, ckpt_round_id, tc_name, tc_args,
                                       risk_level, True, out,
                                       status="error", error=out[:200])
                        else:
                            _emit_tool(session_id, ckpt_round_id, tc_name, tc_args,
                                       risk_level, True, out)

                    if not tool_calls_raw:
                        break

                    # 构建下一轮请求
                    msgs = symbix_client._build_messages(history, user_input, registry=skill_registry, tools=mcp_tools, image_parts=None)
                    msgs.append({"role": "assistant", "content": full_text or None,
                                 "tool_calls": [{"id": t["id"], "type": "function", "function": {"name": t["name"], "arguments": t.get("arguments", "{}")}} for t in tool_calls_raw]})
                    for tr in new_results:
                        msgs.append({"role": "tool", "tool_call_id": tr["tool_call_id"], "name": tr["name"], "content": tr["content"]})

                    tool_calls_raw = None
                    full_text_round = ""
                    _batcher2 = _DeltaBatcher()
                    if ptype == "anthropic":
                        async for e in symbix_client._stream_anthropic(url, headers, model_name, msgs, mcp_tools):
                            if e["type"] == "stream_reset":
                                full_text_round = ""
                                _batcher2 = _DeltaBatcher()
                                yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                                continue
                            for _sse in _batch_yield(e, _batcher2):
                                yield _sse
                            if e["type"] == "delta":
                                full_text_round += e["content"]
                            elif e["type"] == "done":
                                tool_calls_raw = e.get("tool_calls")
                                if e.get("error"):
                                    print(f"[_stream_approve] 内容不完整: {e['error']}")
                    elif ptype == "gemini":
                        async for e in symbix_client._stream_gemini(url, headers, msgs, mcp_tools):
                            if e["type"] == "stream_reset":
                                full_text_round = ""
                                _batcher2 = _DeltaBatcher()
                                yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                                continue
                            for _sse in _batch_yield(e, _batcher2):
                                yield _sse
                            if e["type"] == "delta":
                                full_text_round += e["content"]
                            elif e["type"] == "done":
                                tool_calls_raw = e.get("tool_calls")
                                if e.get("error"):
                                    print(f"[_stream_approve] 内容不完整: {e['error']}")
                    else:
                        async for e in symbix_client._stream_openai_compat(url, headers, model_name, msgs, mcp_tools):
                            if e["type"] == "stream_reset":
                                full_text_round = ""
                                _batcher2 = _DeltaBatcher()
                                yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                                continue
                            for _sse in _batch_yield(e, _batcher2):
                                yield _sse
                            if e["type"] == "delta":
                                full_text_round += e["content"]
                            elif e["type"] == "reasoning":
                                last_reasoning = e.get("content")
                            elif e["type"] == "done":
                                tool_calls_raw = e.get("tool_calls")
                                if e.get("reasoning"):
                                    last_reasoning = e.get("reasoning")
                                if e.get("error"):
                                    print(f"[_stream_approve] 内容不完整: {e['error']}")
                    flushed2 = _batcher2.flush()
                    if flushed2 is not None:
                        yield flushed2
                    if full_text_round:
                        full_text = full_text_round

                if not full_text:
                    full_text = "[已完成工具调用，但模型未返回最终文本。]"
                memory.add(session_id, "assistant", full_text)
                yield format_sse({"type": "done", "content": full_text, "act_mode": act_mode, "act_plan": act_plan})
                # — checkpoint: approve-stream 本轮完成 → 记 round 总结点
                _emit_round_summary(
                    session_id, ckpt_round_id,
                    user_input, full_text, last_reasoning,
                    ckpt_tool_count, ckpt_failed,
                    duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                )
                yield "\n"

                asyncio.create_task(maybe_compress_session(session_id, api_key or "", api_base or "", model or ""))
                asyncio.create_task(maybe_extract_memories(session_id, api_key or "", api_base or "", model or ""))
            except asyncio.CancelledError:
                return
            except Exception as e:
                import traceback
                traceback.print_exc()
                yield format_sse({"type": "error", "content": str(e)})
                yield "datan"
            finally:
                _processing_approvals.discard(req.approval_id)

    except Exception as exc:
        # 工具执行或生成器构建阶段失败
        error_text = f"审批处理失败: {exc}"
        memory.add(ctx["session_id"], "assistant", error_text)
        return {
            "status": "ok",
            "content": error_text,
            "session_id": ctx["session_id"],
            "reasoning": ctx.get("last_reasoning"),
            "steps": steps,
            "act_mode": act_mode,
            "act_plan": act_plan,
            "continuation_error": str(exc),
        }

    return StreamingResponse(_stream_approve(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """AI 流式对话接口 (SSE) - 支持完整的 tool_calls 循环和审批"""

    async def generate():
        try:
            api_key = request.api_key
            api_base = request.api_base
            model = request.model or provider_registry.get_active().model

            user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
            # 有图片时，异步探测模型视觉能力并按需降级
            image_parts = await _filter_image_parts(image_parts, model, api_key, api_base)
            mem_msg = request.message
            if request.attachments:
                names = [
                    (a.filename or a.name or a.path or "file")
                    for a in request.attachments
                ]
                mem_msg = (mem_msg + "\n" if mem_msg else "") + " ".join(
                    f"[文件: {n}]" for n in names
                )
            memory.add(request.session_id, "user", mem_msg)
            history = memory.get_compressed_history(request.session_id, recent_limit=20)
            act_decision = act_mode_controller.decide(mem_msg, history[:-1])
            act_mode = act_decision.judgment.mode.value
            act_plan = act_decision.plan

            # 注入 RAG 记忆到 system prompt
            use_mem = getattr(request, "use_memory", True)
            enriched_prompt = build_system_prompt(
                base=request.system_prompt,
                use_memory=use_mem,
                user_query=mem_msg,
                session_id=request.session_id,
            )
            if act_mode == "reactive":
                enriched_prompt += (
                    "\n\n[Act Mode: reactive]\n"
                    "直接回应当前请求,保持简洁;如果需要工具,先判断必要性再行动。"
                )
            else:
                plan_text = "\n".join(f"{i}. {step}" for i, step in enumerate(act_plan, 1))
                enriched_prompt += (
                    "\n\n[Act Mode: plan_solve]\n"
                    "请遵循以下行为计划,并在工具结果后继续检查和调整:\n"
                    f"{plan_text}\n"
                    "完成后进行简短反思,确认是否满足用户原始目标。"
                )
            symbix_client.system_prompt = enriched_prompt

            # native 工具始终可用；use_mcp 仅附带外部 MCP
            if request.use_mcp:
                mcp_tools = tool_registry.get_openai_tools()
            else:
                mcp_tools = tool_registry.native.get_openai_tools()


            steps = []
            full_text = ""
            tool_calls_raw = None
            # 本轮 user_msg → agent 的 checkpoint 标识。整轮中所有 tool_call 与最后的 round 总结点共用.
            ckpt_round_id = _new_round_id()
            ckpt_tool_count = 0
            ckpt_failed = 0
            ckpt_start_ts = asyncio.get_event_loop().time()

            if parsed_atts:
                yield format_sse({
                    "type": "attachments_parsed",
                    "count": len(parsed_atts),
                    "files": [
                        {
                            "filename": p.get("filename"),
                            "kind": p.get("kind"),
                            "path": p.get("path"),
                            "status": p.get("status"),
                        }
                        for p in parsed_atts
                    ],
                })

            _batcher = _DeltaBatcher()
            async for event in symbix_client.chat_stream(
                user_input=user_for_llm,
                history=history[:-1],
                registry=skill_registry,
                tools=mcp_tools,
                override_api_key=api_key or None,
                override_api_base=api_base or None,
                override_model=model or None,
                image_parts=image_parts or None,
            ):
                if event["type"] == "stream_reset":
                    # 上游连接中断，前端已渲染的这部分内容作废，通知其清空重新开始
                    full_text = ""
                    _batcher = _DeltaBatcher()
                    yield format_sse({"type": "content_reset", "reason": event.get("reason")})
                    continue

                for _sse in _batch_yield(event, _batcher):
                    yield _sse
                if event["type"] == "delta":
                    full_text += event["content"]
                elif event["type"] == "done":
                    full_text = event.get("content") or full_text
                    tool_calls_raw = event.get("tool_calls")
                    if event.get("error"):
                        print(f"[chat_stream] 内容不完整: {event['error']}")

            flushed = _batcher.flush()
            if flushed is not None:
                yield format_sse(flushed)

            max_rounds = 25
            round_count = 0
            last_reasoning = None
            attempted_tool_calls = set()
            # 按工具名统计调用频次，防止模型“以不同参数反复调同一写入工具”陷入死循环
            tool_name_counts: dict[str, int] = {}
            # 写入/创建类工具（对同一会话重复运行是不正常的）
            WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                           "delete_file", "create_skill", "run_command",
                           "open_terminal"}
            MAX_WRITE_CALLS_PER_NAME = 3

            while tool_calls_raw and round_count < max_rounds:
                # 客户端断连检测：前端 abort / 删 session 会断 SSE 连接，后端需主动停、避免后端继续跑 tool。
                if await http_request.is_disconnected():
                    print(f"[stream] client disconnected at round {round_count}, stopping generation")
                    break
                round_count += 1

                steps.append({
                    "type": "tool_calls",
                    "reasoning": last_reasoning,
                    "tool_calls": [
                        {"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                        for tc in tool_calls_raw
                    ],
                })
                yield format_sse({"type": "steps", "steps": steps})

                for tc in tool_calls_raw:
                    tc_id = tc["id"]
                    tc_name = tc["name"]
                    tc_args = tc.get("arguments", "{}")

                    try:
                        parsed_args = (
                            _json.loads(tc_args)
                            if isinstance(tc_args, str) else tc_args
                        )
                        call_signature = (
                            tc_name,
                            _json.dumps(parsed_args, ensure_ascii=False, sort_keys=True),
                        )
                    except (TypeError, _json.JSONDecodeError):
                        call_signature = (tc_name, str(tc_args))

                    if call_signature in attempted_tool_calls:
                        repeated_error = (
                            f"[Error] Tool '{tc_name}' was called again with the same "
                            "arguments. Do not retry unchanged; correct the arguments "
                            "or explain the limitation to the user."
                        )
                        steps.append({
                            "type": "tool_result",
                            "tool_call_id": tc_id,
                            "name": tc_name,
                            "content": repeated_error,
                        })
                        yield format_sse({
                            "type": "tool_result",
                            "id": tc_id,
                            "name": tc_name,
                            "content": repeated_error,
                        })
                        tool_calls_raw = None
                        full_text = full_text or repeated_error
                        break
                    attempted_tool_calls.add(call_signature)

                    # 额外频次检测：同一写入类工具名若被调用超过 MAX 则强制终止循环。
                    if tc_name in WRITE_TOOLS:
                        tool_name_counts[tc_name] = tool_name_counts.get(tc_name, 0) + 1
                        if tool_name_counts[tc_name] > MAX_WRITE_CALLS_PER_NAME:
                            stop_hint = (
                                f"[System] 工具 `{tc_name}` 已被调用 "
                                f"{tool_name_counts[tc_name] - 1} 次。看起来你在重复/近似调用同一写入工具。"
                                "请立即停下来，向用户总结已完成的工作、实际结果、未完成项与原因，"
                                "不要再调用任何写入/创建类工具。"
                            )
                            steps.append({
                                "type": "tool_result",
                                "tool_call_id": tc_id,
                                "name": tc_name,
                                "content": stop_hint,
                            })
                            yield format_sse({
                                "type": "tool_result",
                                "id": tc_id,
                                "name": tc_name,
                                "content": stop_hint,
                            })
                            tool_calls_raw = None
                            full_text = full_text or stop_hint
                            break

                    # 动态风险分级：根据工具名和参数判断是否需要审批
                    risk_level, risk_reason = classify_tool_risk(tc_name, tc_args)
                    
                    # SAFE 级别直接放行，MEDIUM 和 HIGH 需要审批
                    if risk_level in (ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH):
                        approval_id = str(uuid.uuid4())
                        _pending_approvals[approval_id] = {
                            "session_id": request.session_id,
                            "user_input": user_for_llm,
                            "history": history[:-1],
                            "mcp_tools": mcp_tools,
                            "api_key": api_key,
                            "api_base": api_base,
                            "model": model,
                            "steps": steps,
                            "last_reasoning": last_reasoning,
                            "round_count": round_count,
                            "full_text": full_text,
                            "act_mode": act_mode,
                            "act_plan": act_plan,
                            "pending_tc": {
                                "id": tc_id,
                                "name": tc_name,
                                "arguments": tc_args,
                            },
                            "ckpt_round_id": ckpt_round_id,
                            "remaining_tcs": [
                                {
                                    "id": r["id"],
                                    "name": r["name"],
                                    "arguments": r.get("arguments", "{}"),
                                }
                                for r in tool_calls_raw
                            ],
                        }

                        yield format_sse({
                            "type": "await_approval",
                            "approval_id": approval_id,
                            "tool": {"id": tc_id, "name": tc_name, "arguments": tc_args},
                            "risk_level": risk_level,
                            "risk_reason": risk_reason,
                            "act_mode": act_mode,
                            "act_plan": act_plan,
                        })
                        # — checkpoint: 需审批工具被拦住 → 记一条 skipped
                        ckpt_tool_count += 1
                        _emit_tool(request.session_id, ckpt_round_id, tc_name, tc_args,
                                   risk_level, False, "", status="skipped",
                                   error="awaiting user approval")
                        yield format_sse({"type": "done", "content": full_text})
                        # — checkpoint: 本轮被审批拦住,尚未完成 → round 未完待续
                        _emit_round_summary(
                            request.session_id, ckpt_round_id,
                            mem_msg, full_text, last_reasoning,
                            ckpt_tool_count, ckpt_failed,
                            duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                        )
                        return

                    tool_output = tool_registry.execute(tc_name, tc_args)
                    if not isinstance(tool_output, str):
                        tool_output = _json.dumps(tool_output, ensure_ascii=False)
                    steps.append({
                        "type": "tool_result",
                        "tool_call_id": tc_id,
                        "name": tc_name,
                        "content": tool_output,
                    })
                    yield format_sse({
                        "type": "tool_result",
                        "id": tc_id,
                        "name": tc_name,
                        # 工具结果必须完整传给前端。这里之前只发送前 200 个字符,
                        # 会把 JSON 结果截断,看起来像被 SSE 分割成了多段。
                        "content": tool_output,
                    })
                    # — checkpoint: 记一条工具调用 (SAFE 自动放行的)
                    ckpt_tool_count += 1
                    if isinstance(tool_output, str) and tool_output.startswith("[Error"):
                        ckpt_failed += 1
                        _emit_tool(request.session_id, ckpt_round_id, tc_name, tc_args,
                                   risk_level, True, tool_output, status="error",
                                   error=tool_output[:200])
                    else:
                        _emit_tool(request.session_id, ckpt_round_id, tc_name, tc_args,
                                   risk_level, True, tool_output)

                # 已经发现完全重复的调用时,不要再把空的 tool_calls 请求发回模型。
                if not tool_calls_raw:
                    break

                tool_results = [
                    {
                        "tool_call_id": t["id"],
                        "role": "tool",
                        "name": t["name"],
                        "content": steps[-len(tool_calls_raw) + i]["content"]
                        if i < len(steps)
                        and steps[-len(tool_calls_raw) + i]["type"] == "tool_result"
                        else "{}",
                        "arguments": t.get("arguments", "{}"),
                    }
                    for i, t in enumerate(tool_calls_raw)
                ]

                msgs = symbix_client._build_messages(
                    history[:-1],
                    user_for_llm,
                    registry=skill_registry,
                    tools=mcp_tools,
                    image_parts=image_parts or None,
                )

                msgs.append({
                    "role": "assistant",
                    "content": full_text or None,
                    "tool_calls": [
                        {
                            "id": t["id"],
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "arguments": t.get("arguments", "{}"),
                            },
                        }
                        for t in tool_calls_raw
                    ],
                })
                for tr in tool_results:
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tr["tool_call_id"],
                        "name": tr["name"],
                        "content": tr["content"],
                    })

                provider = provider_registry.get_active()
                raw_model = model or provider.model
                raw_base = api_base or provider.api_base
                api_key_val = api_key or provider.api_key
                url, ptype, headers, model_name = symbix_client._resolve_endpoint(
                    raw_model, raw_base, api_key_val
                )

                tool_calls_raw = None
                full_text_round = ""
                if ptype == "anthropic":
                    async for e in symbix_client._stream_anthropic(
                        url, headers, model_name, msgs, mcp_tools
                    ):
                        if e["type"] == "stream_reset":
                            full_text_round = ""
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                elif ptype == "gemini":
                    async for e in symbix_client._stream_gemini(
                        url, headers, msgs, mcp_tools
                    ):
                        if e["type"] == "stream_reset":
                            full_text_round = ""
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                else:
                    async for e in symbix_client._stream_openai_compat(
                        url, headers, model_name, msgs, mcp_tools
                    ):
                        if e["type"] == "stream_reset":
                            full_text_round = ""
                            yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                            continue
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "reasoning":
                            last_reasoning = e.get("content")
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                            if e.get("reasoning"):
                                last_reasoning = e.get("reasoning")
                            if e.get("error"):
                                print(f"[chat_stream 轮次] 内容不完整: {e['error']}")

                if full_text_round:
                    full_text = full_text_round

            # 工具轮次用尽或不再有 tool_calls 后，若模型未给出最终文本，
            # 给出兑底提示，避免前端看起来“卡住/空回复”。
            if not full_text:
                full_text = (
                    f"[已完成 {round_count} 轮工具调用，但模型未返回最终文本。"
                    "可能已达到工具调用上限，请继续提问以推进。]"
                )

            memory.add(request.session_id, "assistant", full_text)
            yield format_sse({
                "type": "done",
                "content": full_text,
                "act_mode": act_mode,
                "act_plan": act_plan,
            })
            # — checkpoint: 一轮 user_msg → agent 完成,记 round 总结点
            _emit_round_summary(
                request.session_id, ckpt_round_id,
                mem_msg, full_text, last_reasoning,
                ckpt_tool_count, ckpt_failed,
                duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
            )
            yield "data: [DONE]\n\n"

            asyncio.create_task(maybe_compress_session(
                request.session_id, api_key or "", api_base or "", model or ""))
            asyncio.create_task(maybe_extract_memories(
                request.session_id, api_key or "", api_base or "", model or ""))

        except asyncio.CancelledError:
            # 客户端主动中止 SSE、浏览器关闭页面或服务热重载时,Starlette 会取消
            # 当前生成器。取消属于正常的连接生命周期事件,不要把它当成业务异常
            # 再发送 error SSE 或打印 traceback。
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield format_sse({"type": "error", "content": str(e)})
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    try:
        history = memory.get_history(session_id, limit=limit)
        summary = memory.get_summary(session_id)
        return {
            "session_id": session_id,
            "messages": history,
            "summary": summary["summary"] if summary else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
