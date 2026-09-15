"""非流式对话路由:/chat。"""
import asyncio
import uuid
import json as _json

from fastapi import APIRouter, HTTPException, Request
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
)
from application.services.risk_context import classify_for_chat, maybe_apply_trust_command
from application.services.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
    build_system_prompt,
)
from Symbix_sdk.checkpoint import set_current as _ctx_set_current
from application.routers.chat.helpers import (
    _INTERACTION_TOOLS,
    _is_interaction_tool,
    _parse_interaction_request,
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

@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    try:
        api_key = request.api_key or provider_registry.get_active().api_key
        api_base = request.api_base or provider_registry.get_active().api_base
        model = request.model or provider_registry.get_active().model

        user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
        # auto-pilot 自然语言开关指令(消费时替换为提示占位)
        user_for_llm, _consumed = maybe_apply_trust_command(request.session_id, user_for_llm)
        # 有图片时,异步探测模型视觉能力并按需降级
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
        yield format_sse({"type": "round_id", "round_id": ckpt_round_id})

        max_tool_rounds = 25
        round_count = 0
        nonstream_name_counts: dict[tuple, int] = {}  # key = (工具名, 参数签名),仅同签名计数
        # 多轮工具累积基座:整个 agent 循环内只初始化一次,
        # 之后每轮增量 append,避免模型对前几轮工具"失忆"。
        running_msgs: list[dict] | None = None
        # 跨轮去重集合(与 chat_stream 一致的语义:同参数工具只调一次)。
        attempted_tool_calls: set[tuple] = set()
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
                    {"id": tc["id"], "name": tc.get("name"), "arguments": tc.get("arguments")}
                    for tc in response["tool_calls"]
                ],
            })

            for idx_tc, tc in enumerate(response["tool_calls"]):
                fn = tc  # dict: {id, name, arguments}
                # 解析参数用于风险分级
                try:
                    args = _json.loads(fn["arguments"]) if isinstance(fn.get("arguments"), str) else fn.get("arguments")
                except Exception:
                    args = {}

                # 同参数去重:同一工具+参数在本轮内已调用过 → 拦下并注入合成结果。
                try:
                    sig = (fn["name"], _json.dumps(args, ensure_ascii=False, sort_keys=True))
                except (TypeError, _json.JSONDecodeError):
                    sig = (fn["name"], str(fn.get("arguments")))
                if sig in attempted_tool_calls:
                    dup_msg = (
                        f"[System] 工具 `{fn['name']}` 在本轮已用相同参数调用过,已阻止重复执行。"
                        "请基于上文的工具结果继续推进;若确实需要最新状态/重跑,"
                        "请更换参数或向用户说明理由,不要原样重试。"
                    )
                    tool_results.append({
                        "tool_call_id": fn["id"],
                        "role": "tool",
                        "name": fn["name"],
                        "content": dup_msg,
                        "arguments": fn.get("arguments"),
                    })
                    steps.append({
                        "type": "tool_result",
                        "tool_call_id": fn["id"],
                        "name": fn["name"],
                        "content": dup_msg,
                        "synthetic": True,
                    })
                    continue
                attempted_tool_calls.add(sig)

                # 频次反循环:同一工具+相同参数(签名)反复调用 → 直接跳出循环并记录停止原因
                if fn["name"] in NONSTREAM_WRITE_TOOLS:
                    nonstream_name_counts[sig] = nonstream_name_counts.get(sig, 0) + 1
                    if nonstream_name_counts[sig] > MAX_NS_WRITE:
                        stop_hint = (
                            f"[System] 工具 `{fn['name']}` 已用相同参数被调用 "
                            f"{nonstream_name_counts[sig] - 1} 次。"
                            "请停止重复调用,直接向用户总结已完成的工作与原因,不要继续调用任何写入类工具。"
                        )
                        tool_results.append({
                            "tool_call_id": fn["id"],
                            "role": "tool",
                            "name": fn["name"],
                            "content": stop_hint,
                            "arguments": fn.get("arguments"),
                        })
                        steps.append({
                            "type": "tool_result",
                            "tool_call_id": fn["id"],
                            "name": fn["name"],
                            "content": stop_hint,
                        })
                        # 强制跳出 while 循环
                        response = {"content": stop_hint, "tool_calls": None, "reasoning": last_reasoning}
                        break

                # 使用风险分级器判断是否需要审批(通道化 + 会话信任)
                _risk, _needs_approval, _ = classify_for_chat(
                    fn["name"], args, mcp_tools, request.session_id,
                )
                risk_level, risk_reason = _risk.level, _risk.reason

                # 交互型工具(ask_clarifying_question):强制走"提问审批" ——
                # 先真执行拿到 question/suggestions,再挂起等用户回答,不发普通 tool_result。
                if _is_interaction_tool(fn["name"]):
                    _ctx_set_current(request.session_id, ckpt_round_id)
                    tool_output = tool_registry.execute(fn["name"], fn.get("arguments"))
                    if not isinstance(tool_output, str):
                        tool_output = _json.dumps(tool_output, ensure_ascii=False)
                    qdata = _parse_interaction_request(tool_output)
                    if qdata:
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
                            "pending_tc": {"id": fn["id"], "name": fn["name"], "arguments": fn.get("arguments")},
                            "ckpt_round_id": ckpt_round_id,
                            "tool_chain_msgs": _steps_to_tool_messages(steps),
                            "attempted_tool_calls": attempted_tool_calls,
                            "tool_name_counts": nonstream_name_counts,
                            "remaining_tcs": [
                                {"id": r["id"], "name": r.get("name"), "arguments": r.get("arguments")}
                                for r in response["tool_calls"][idx_tc + 1:]
                            ],
                            "risk_level": risk_level,
                            "risk_reason": risk_reason,
                            "risk": _risk,
                        }
                        _pending_questions[approval_id] = {
                            "question": qdata.get("question", ""),
                            "suggestions": qdata.get("suggestions", []),
                            "context": qdata.get("context", ""),
                        }
                        # — checkpoint: 提问挂起 → 记 skipped + round 未完待续
                        ckpt_tool_count += 1
                        _emit_tool(request.session_id, ckpt_round_id, fn["name"], fn.get("arguments"),
                                   risk_level, False, "", status="skipped",
                                   error="awaiting user input")
                        _emit_round_summary(
                            request.session_id, ckpt_round_id,
                            mem_msg, "", last_reasoning,
                            ckpt_tool_count, ckpt_failed,
                            duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                        )
                        yield format_sse({
                            "type": "await_input",
                            "input_id": approval_id,
                            "question": qdata.get("question", ""),
                            "suggestions": qdata.get("suggestions", []),
                            "context": qdata.get("context", ""),
                            "tool": {"id": fn["id"], "name": fn["name"]},
                        })
                        return
                    # 非 pending 返回(如 question 为空):降级为普通 tool_result,继续执行

                # needs_approval=False(read/auto 放行)直接执行;True 进审批
                if _needs_approval:
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
                        "pending_tc": {"id": fn["id"], "name": fn["name"], "arguments": fn.get("arguments")},
                        "ckpt_round_id": ckpt_round_id,
                        # 审批快照带上前置 SAFE 工具链 + 去重集合,续跑不失忆不重复。
                        "tool_chain_msgs": _steps_to_tool_messages(steps),
                        "attempted_tool_calls": attempted_tool_calls,
                        "tool_name_counts": nonstream_name_counts,
                        # 只保留审批工具之后尚未执行的调用。
                        "remaining_tcs": [
                            {"id": r["id"], "name": r.get("name"), "arguments": r.get("arguments")}
                            for r in response["tool_calls"][idx_tc + 1:]
                        ],
                        "risk_level": risk_level,
                        "risk_reason": risk_reason,
                        "risk": _risk,
                    }

                    # — checkpoint: 需审批工具被拦 → 记 skipped + round 未完待续
                    ckpt_tool_count += 1
                    _emit_tool(request.session_id, ckpt_round_id, fn["name"], fn.get("arguments"),
                               risk_level, False, "", status="skipped",
                               error="awaiting user approval")
                    _emit_round_summary(
                        request.session_id, ckpt_round_id,
                        mem_msg, "", last_reasoning,
                        ckpt_tool_count, ckpt_failed,
                        duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                    )
                    yield format_sse({
                        "type": "await_approval",
                        "approval_id": approval_id,
                        "session_id": request.session_id,
                        "risk_level": risk_level,
                        "risk_reason": risk_reason,
                        "tool": {
                            "tool_call_id": fn["id"],
                            "name": fn["name"],
                            "arguments": fn.get("arguments"),
                        },
                    })
                    return

                _ctx_set_current(request.session_id, ckpt_round_id)
                tool_output = tool_registry.execute(fn["name"], fn.get("arguments"))
                if not isinstance(tool_output, str):
                    tool_output = _json.dumps(tool_output, ensure_ascii=False)
                tool_results.append({
                    "tool_call_id": fn["id"],
                    "role": "tool",
                    "name": fn["name"],
                    "content": tool_output,
                    "arguments": fn.get("arguments"),
                })
                steps.append({
                    "type": "tool_result",
                    "tool_call_id": fn["id"],
                    "name": fn["name"],
                    "content": tool_output,
                })
                print(f"[MCP Tool] {fn['name']} -> {tool_output[:200]}")
                # — checkpoint: 记一条工具调用 (非流 /chat 路径)
                ckpt_tool_count += 1
                if isinstance(tool_output, str) and tool_output.startswith("[Error"):
                    ckpt_failed += 1
                    _emit_tool(request.session_id, ckpt_round_id, fn["name"], fn.get("arguments"),
                               risk_level, True, tool_output,
                               status="error", error=tool_output[:200])
                else:
                    _emit_tool(request.session_id, ckpt_round_id, fn["name"], fn.get("arguments"),
                               risk_level, True, tool_output)

            # 多轮累积:running_msgs 只初始化一次(history + user 基底),
            # 每轮在其上 append 本轮 assistant(tool_calls)+tool 结果,
            # 使后续轮模型能看到前面所有已执行工具,不再每轮重建导致"失忆"。
            provider = provider_registry.get_active()
            raw_model = model or provider.model
            raw_base = api_base or provider.api_base
            api_key_val = api_key or provider.api_key
            if running_msgs is None:
                running_msgs = symbix_client._build_messages(
                    history[:-1],
                    user_for_llm,
                    registry=skill_registry,
                    tools=mcp_tools,
                    image_parts=image_parts or None,
                )
            symbix_client._build_tool_result_messages(running_msgs, tool_results)
            _assert_tool_pairing(running_msgs, strict=False)
            if sum(_estimate_tool_tokens(str(m.get("content", ""))) for m in running_msgs) > MAX_CUM_TOOL_TOKENS:
                print(f"[chat] 工具结果累积超限,终止工具循环")
                response = {"content": "[已完成较多工具调用,为避免上下文过长提前收尾。]",
                            "tool_calls": None, "reasoning": None}
                last_reasoning = None
                break
            response = await symbix_client._chat_raw(
                running_msgs, mcp_tools, raw_model, raw_base, api_key_val
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

        yield format_sse({"type": "done", "content": assistant_content,
                          "reasoning": last_reasoning, "steps": steps,
                          "act_mode": act_mode, "act_plan": act_plan})
        yield "data: [DONE]\n\n"
        return
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
