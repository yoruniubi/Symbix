"""流式对话路由:/chat/stream, /history。"""
import asyncio
import uuid
import json as _json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from application.schemas import ChatRequest
from application.state import (
    memory,
    provider_registry,
    skill_registry,
    symbix_client,
    act_mode_controller,
    tool_registry,
    _pending_approvals,
    _pending_questions,
    register_session_task,
    unregister_session_task,
)
from application.services.risk_context import classify_for_chat, maybe_apply_trust_command
from application.services.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
    build_system_prompt,
)
from Symbix_sdk.checkpoint import (
    set_current as _ctx_set_current,
    get_recorder as _get_recorder,
)
from application.routers.chat.helpers import (
    _INTERACTION_TOOLS,
    _is_interaction_tool,
    _parse_interaction_request,
    _DeltaBatcher,
    _batch_yield,
    _new_round_id,
    _emit_tool,
    _emit_round_summary,
    _estimate_tool_tokens,
    _steps_to_tool_messages,
    _assert_tool_pairing,
    _prepare_user_message,
    _filter_image_parts,
    MAX_CUM_TOOL_TOKENS,
)

router = APIRouter(tags=["chat"])

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, http_request: Request):
    """AI 流式对话接口 (SSE) - 支持完整的 tool_calls 循环和审批"""

    async def generate():
        # 注册本会话进行中任务:删除对话时可一并取消,终止 chat/action。
        _gen_task = asyncio.current_task()
        register_session_task(request.session_id, _gen_task)
        try:
            # ── 重试标记：如果前端传了 superseded_round_id，标记旧 round ──
            if request.superseded_round_id:
                try:
                    _get_recorder().store.mark_round_superseded(
                        request.session_id, request.superseded_round_id
                    )
                except Exception:
                    pass

            api_key = request.api_key
            api_base = request.api_base
            model = request.model or provider_registry.get_active().model

            user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
            # auto-pilot 自然语言开关指令(消费时替换为提示占位)
            user_for_llm, _consumed = maybe_apply_trust_command(request.session_id, user_for_llm)
            # 有图片时,异步探测模型视觉能力;无视觉模型降级在 client._build_messages 内(取色+文本)
            image_parts, supports_vision = await _filter_image_parts(image_parts, model, api_key, api_base)
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
            last_reasoning = None
            # 本轮 user_msg → agent 的 checkpoint 标识。整轮中所有 tool_call 与最后的 round 总结点共用.
            ckpt_round_id = _new_round_id()
            ckpt_tool_count = 0
            ckpt_failed = 0
            ckpt_start_ts = asyncio.get_event_loop().time()
            yield format_sse({"type": "round_id", "round_id": ckpt_round_id})

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
                supports_vision=supports_vision,
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
                elif event["type"] == "reasoning":
                    # DeepSeek/Groq 等带 reasoning_content 的模型首轮也会吐推理增量。
                    # 需要拼上，否则 round 总结点的 reasoning_snippet 永远为空。
                    last_reasoning = (last_reasoning or "") + (event.get("content") or "")
                elif event["type"] == "done":
                    full_text = event.get("content") or full_text
                    tool_calls_raw = event.get("tool_calls")
                    if event.get("reasoning"):
                        last_reasoning = event.get("reasoning")
                    if event.get("error"):
                        print(f"[chat_stream] 内容不完整: {event['error']}")

            flushed = _batcher.flush()
            if flushed is not None:
                yield format_sse(flushed)

            max_rounds = 25
            round_count = 0
            # last_reasoning 已在首轮循环前初始化,这里不再覆盖。
            attempted_tool_calls = set()
            # 按(工具名, 参数)签名统计:仅同参数反复调用才触发,不同参数(如连续改不同文件)不误伤
            tool_name_counts: dict[tuple, int] = {}
            # 写入/创建类工具(对同一会话重复运行是不正常的)
            WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                           "delete_file", "create_skill", "run_command",
                           "open_terminal"}
            MAX_WRITE_CALLS_PER_NAME = 3

            # —— 多轮工具上下文累积 ——
            # 首轮流结束后,以与首轮请求一致的 messages 为基底(history + user),
            # 之后每轮把本轮的 assistant(tool_calls)+tool 结果 append 进来,
            # 让后续轮模型能看到前面所有已执行的工具,不再每轮从空 history 重建。
            running_msgs = symbix_client._build_messages(
                history[:-1],
                user_for_llm,
                registry=skill_registry,
                tools=mcp_tools,
                image_parts=image_parts or None,
                supports_vision=supports_vision,
            )
            cum_tool_tokens = 0

            while tool_calls_raw and round_count < max_rounds:
                # 客户端断连检测:前端 abort / 删 session 会断 SSE 连接,后端需主动停、避免后端继续跑 tool。
                if await http_request.is_disconnected():
                    print(f"[stream] client disconnected at round {round_count}, stopping generation")
                    break
                round_count += 1
                # 本轮实际执行(拿到结果)的工具,供轮末累积进 running_msgs。
                round_results: list[dict] = []
                # 本轮被"重复拦截"注入合成结果的次数;若模型无视提示持续重复,
                # 连续多次合成无真实执行说明陷入死循环 → 强制收尾。
                synthetic_count = 0

                steps.append({
                    "type": "tool_calls",
                    "reasoning": last_reasoning,
                    "tool_calls": [
                        {"id": tc["id"], "name": tc["name"], "arguments": tc["arguments"]}
                        for tc in tool_calls_raw
                    ],
                })
                yield format_sse({"type": "steps", "steps": steps})

                for idx_tc, tc in enumerate(tool_calls_raw):
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
                        # 同一工具+相同参数在本轮内已被调用过:不再真实执行,
                        # 而是向模型注入一条合成结果,让它基于已有结果继续或调整参数。
                        repeated_error = (
                            f"[System] 工具 `{tc_name}` 在本轮已用相同参数调用过,已阻止重复执行。"
                            "请基于上文的工具结果继续推进;若确实需要最新状态/重跑,"
                            "请更换参数或向用户说明理由,不要原样重试。"
                        )
                        steps.append({
                            "type": "tool_result",
                            "tool_call_id": tc_id,
                            "name": tc_name,
                            "content": repeated_error,
                            "synthetic": True,
                        })
                        yield format_sse({
                            "type": "tool_result",
                            "id": tc_id,
                            "name": tc_name,
                            "content": repeated_error,
                        })
                        # 合成结果同样累积进 running_msgs,让模型看到"已被拦"。
                        round_results.append({
                            "tool_call_id": tc_id,
                            "role": "tool",
                            "name": tc_name,
                            "content": repeated_error,
                            "arguments": tc_args,
                        })
                        synthetic_count += 1
                        # 若连续多次重复仍被模型无视 → 直接结束整个工具循环,不再空转。
                        if synthetic_count >= 2:
                            tool_calls_raw = None
                            full_text = full_text or repeated_error
                            break
                        # 跳过该重复调用,继续处理同轮其余工具(而非直接中断整轮)。
                        continue
                    attempted_tool_calls.add(call_signature)

                    # 额外频次检测:同一工具+相同参数(签名)反复调用超过阈值才强制终止循环。
                    if tc_name in WRITE_TOOLS:
                        tool_name_counts[call_signature] = tool_name_counts.get(call_signature, 0) + 1
                        if tool_name_counts[call_signature] > MAX_WRITE_CALLS_PER_NAME:
                            stop_hint = (
                                f"[System] 工具 `{tc_name}` 已用相同参数被调用 "
                                f"{tool_name_counts[call_signature] - 1} 次。看起来你在重复调用同一工具。"
                                "请立即停下来,向用户总结已完成的工作、实际结果、未完成项与原因,"
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

                    # 动态风险分级:根据工具名和参数判断是否需要审批(通道化 + 会话信任)
                    _risk, _needs_approval, _ = classify_for_chat(
                        tc_name, tc_args, mcp_tools, request.session_id,
                    )
                    risk_level, risk_reason = _risk.level, _risk.reason

                    # 交互型工具(ask_clarifying_question):先真执行拿 question/suggestions,
                    # 再挂起等用户回答,发 await_input 事件(前端渲染成提问卡),不发普通 tool_result。
                    if _is_interaction_tool(tc_name):
                        _ctx_set_current(request.session_id, ckpt_round_id)
                        tool_output = tool_registry.execute(tc_name, tc_args)
                        if not isinstance(tool_output, str):
                            tool_output = _json.dumps(tool_output, ensure_ascii=False)
                        qdata = _parse_interaction_request(tool_output)
                        if qdata:
                            approval_id = str(uuid.uuid4())
                            tool_chain_msgs = _steps_to_tool_messages(steps)
                            _pending_approvals[approval_id] = {
                                "session_id": request.session_id,
                                "user_input": user_for_llm,
                                "history": history[:-1],
                                "tool_chain_msgs": tool_chain_msgs,
                                "attempted_tool_calls": attempted_tool_calls,
                                "tool_name_counts": tool_name_counts,
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
                                # 提问工具专用标记 + 选项信息
                                "is_question": True,
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
                                    for r in tool_calls_raw[idx_tc + 1:]
                                ],
                                "risk": _risk,
                            }
                            _pending_questions[approval_id] = {
                                "question": qdata.get("question", ""),
                                "suggestions": qdata.get("suggestions", []),
                                "context": qdata.get("context", ""),
                            }
                            # — checkpoint: 提问挂起 → 记 skipped + round 未完待续
                            ckpt_tool_count += 1
                            _emit_tool(request.session_id, ckpt_round_id, tc_name, tc_args,
                                       risk_level, False, "", status="skipped",
                                       error="awaiting user input")
                            yield format_sse({
                                "type": "await_input",
                                "input_id": approval_id,
                                "question": qdata.get("question", ""),
                                "suggestions": qdata.get("suggestions", []),
                                "context": qdata.get("context", ""),
                                "tool": {"id": tc_id, "name": tc_name},
                            })
                            yield format_sse({"type": "done", "content": full_text})
                            # 掉出本轮工具循环,等待用户回答后由 /chat/approve 续跑
                            tool_calls_raw = None
                            break
                        # 非 pending 返回 → 降级为普通 tool_result,继续执行

                    # needs_approval=False(read/auto 放行)直接执行;True 进审批
                    if _needs_approval:
                        approval_id = str(uuid.uuid4())
                        # 审批快照里带上前置 SAFE 工具已执行的"工具链消息",
                        # 并捎带 attempted/频次计数,使跨审批续跑时上下文与去重都连续。
                        tool_chain_msgs = _steps_to_tool_messages(steps)
                        _pending_approvals[approval_id] = {
                            "session_id": request.session_id,
                            "user_input": user_for_llm,
                            "history": history[:-1],
                            "tool_chain_msgs": tool_chain_msgs,
                            "attempted_tool_calls": attempted_tool_calls,
                            "tool_name_counts": tool_name_counts,
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
                            # 只保留本轮尚未执行(在当前审批工具之后)的调用,
                            # 避免 approve 时把审批前已跑过的 SAFE 工具再执行一遍。
                            "remaining_tcs": [
                                {
                                    "id": r["id"],
                                    "name": r["name"],
                                    "arguments": r.get("arguments", "{}"),
                                }
                                for r in tool_calls_raw[idx_tc + 1:]
                            ],
                            "risk": _risk,
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

                    _ctx_set_current(request.session_id, ckpt_round_id)
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
                    # 本轮真实执行的工具结果,轮末统一累积进 running_msgs。
                    round_results.append({
                        "tool_call_id": tc_id,
                        "role": "tool",
                        "name": tc_name,
                        "content": tool_output,
                        "arguments": tc_args,
                    })

                # 已经发现完全重复的调用时,不要再把空的 tool_calls 请求发回模型。
                if not tool_calls_raw:
                    break

                # 把本轮(assistant tool_calls + tool 结果)累积进 running_msgs,
                # 使后续轮模型能看到前面所有已执行工具 —— 不再每轮从 history 重建。
                symbix_client._build_tool_result_messages(running_msgs, round_results)
                _assert_tool_pairing(running_msgs, strict=False)
                # 防上下文无限增长:累计工具结果 token 超限则结束循环。
                cum_tool_tokens += sum(
                    _estimate_tool_tokens(str(tr.get("content", ""))) for tr in round_results
                )
                if cum_tool_tokens > MAX_CUM_TOOL_TOKENS:
                    print(f"[chat_stream] 工具结果累积超限({cum_tool_tokens} tok),终止工具循环")
                    tool_calls_raw = None
                    full_text = full_text or (
                        "[已完成较多工具调用,为避免上下文过长提前收尾。]"
                    )
                    break

                msgs = running_msgs

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
                        url, headers, model_name, msgs, mcp_tools,
                        caps_model_override=raw_model
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
            # 陪伴:任务完成 → 弹幕庆祝(静默失败不影响主流程)
            try:
                from application.services.danmaku_service import emit_danmaku
                emit_danmaku("complete")
            except Exception:
                pass
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
            try:
                interrupted_note = (
                    full_text.rstrip() + "\n\n[本条回复在生成过程中被用户中断。]"
                    if full_text
                    else "[本条回复在生成过程中被用户中断,尚未输出任何内容。]"
                )
                memory.add(request.session_id, "assistant", interrupted_note)
            except Exception:
                pass
            return
        except Exception as e:
            import traceback
            traceback.print_exc()
            # 陪伴:出错 → 弹幕安抚(静默失败不影响主流程)
            try:
                from application.services.danmaku_service import emit_danmaku
                emit_danmaku("error")
            except Exception:
                pass
            yield format_sse({"type": "error", "content": str(e)})
            yield "data: [DONE]\n\n"
        finally:
            unregister_session_task(request.session_id, _gen_task)

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
