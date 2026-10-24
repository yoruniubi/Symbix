"""流式对话路由:/chat/stream, /history。"""
import asyncio
import time as _time
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
    usage_store,
    _pending_approvals,
    _pending_questions,
    register_session_task,
    unregister_session_task,
)
from application.services.risk_context import classify_for_chat, maybe_apply_trust_command
from application.services.round_digest import build_recent_tool_digest
from application.services.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
    build_system_prompt_parts,
)
from Symbix_sdk.checkpoint import (
    set_current as _ctx_set_current,
    get_recorder as _get_recorder,
)
from Symbix_sdk.time_context import current_time_line
from application.routers.chat.helpers import (
    _INTERACTION_TOOLS,
    _is_interaction_tool,
    _parse_interaction_request,
    _DeltaBatcher,
    _batch_yield,
    _client_event,
    _new_round_id,
    _emit_tool,
    _emit_round_summary,
    _estimate_tool_tokens,
    _steps_to_tool_messages,
    _assert_tool_pairing,
    _prepare_user_message,
    _filter_image_parts,
    attachment_history_note,
    _stream_tool_events,
    _is_read_only_parallel_tool,
    run_tools_parallel,
    MAX_CUM_TOOL_TOKENS,
    build_usage_payload,
)

router = APIRouter(tags=["chat"])


def _tool_call_signature(name: str, arguments) -> tuple:
    """工具调用签名(用于本轮去重)。参数解析失败时退化为原字符串。"""
    try:
        parsed = _json.loads(arguments) if isinstance(arguments, str) else arguments
        return (name, _json.dumps(parsed, ensure_ascii=False, sort_keys=True))
    except (TypeError, _json.JSONDecodeError):
        return (name, str(arguments))


def _collect_read_batch(tool_calls_raw: list[dict], start_idx: int,
                        attempted_tool_calls: set, mcp_tools, session_id: str) -> list[tuple]:
    """从 start_idx 起收集**连续**可并行的只读调用。

    返回 [(索引, tc, 签名, 风险等级)]。碰到以下任一情况立刻停止收集,
    把剩下的交给原有的串行路径处理:
      - 非只读工具 / 异步工具(delegate_* 自身已并行) / 交互型工具
      - 本轮已用相同参数调过(要发合成拦截结果)
      - 判定为需审批
    """
    batch: list[tuple] = []
    for j in range(start_idx, len(tool_calls_raw)):
        tc = tool_calls_raw[j]
        name = tc.get("name", "")
        if not _is_read_only_parallel_tool(name) or tool_registry.is_async_tool(name):
            break
        args = tc.get("arguments", "{}")
        sig = _tool_call_signature(name, args)
        # 注意:调用方在进入本函数前已把**当前**这条加进 attempted_tool_calls,
        # 所以 j == start_idx 不查重,否则第一个就 break、批量永远为空。
        if j != start_idx and sig in attempted_tool_calls:
            break
        _risk, _needs, _ = classify_for_chat(name, args, mcp_tools, session_id)
        if _needs:
            break
        batch.append((j, tc, sig, _risk.level))
    return batch

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
            # 本轮 user_msg → agent 的 checkpoint 标识(整轮 tool_call 与轮末总结点共用)。
            # 提前初始化:客户端在轮次早期断开时,取消分支也要能落一条 round 记录。
            ckpt_round_id = _new_round_id()
            ckpt_tool_count = 0
            ckpt_failed = 0
            ckpt_start_ts = asyncio.get_event_loop().time()
            full_text = ""
            last_reasoning = None

            user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
            # auto-pilot 自然语言开关指令(消费时替换为提示占位)
            user_for_llm, _consumed = maybe_apply_trust_command(request.session_id, user_for_llm)
            # 有图片时,异步探测模型视觉能力;无视觉模型降级在 client._build_messages 内(取色+文本)
            image_parts, supports_vision = await _filter_image_parts(image_parts, model, api_key, api_base)
            mem_msg = request.message
            att_note = attachment_history_note(parsed_atts)
            if request.attachments:
                names = [
                    (a.filename or a.name or a.path or "file")
                    for a in request.attachments
                ]
                label = " ".join(f"[文件: {n}]" for n in names)
                att_note = f"{label}\n{att_note}" if att_note else label
            if att_note:
                mem_msg = (mem_msg + "\n" if mem_msg else "") + att_note
            memory.add(request.session_id, "user", mem_msg)
            history = memory.get_compressed_history(request.session_id, recent_limit=20)
            act_decision = act_mode_controller.decide(mem_msg, history[:-1])
            act_mode = act_decision.judgment.mode.value
            act_plan = act_decision.plan

            # 注入 RAG 记忆到 system prompt —— 但 RAG 是「按当轮提问检索」出来的,
            # 放进 system 会让前缀每轮都变(上游 prompt cache 失效)。
            # 因此拆成:稳定部分 → system;当轮变化部分 → 拼在用户消息前面。
            use_mem = getattr(request, "use_memory", True)
            stable_prompt, dyn_mem = build_system_prompt_parts(
                base=request.system_prompt,
                use_memory=use_mem,
                user_query=mem_msg,
                session_id=request.session_id,
            )
            dyn_parts: list[str] = []
            # 当前时间:模型原本完全拿不到系统时间,「本周五」这类相对时间只能猜。
            # 拼在用户消息里而不是 system,保住 system 前缀的 prompt cache。
            dyn_parts.append(current_time_line())
            if dyn_mem:
                dyn_parts.append(dyn_mem)
            # 「最近几轮做了什么」:来自 checkpoint 的工具调用摘要,避免模型为了知道自己做过什么
            # 去重读文件(那更烧 token)。没有工具记录的轮次不产生任何开销。
            tool_digest = build_recent_tool_digest(request.session_id)
            if tool_digest:
                dyn_parts.append(tool_digest)
            if act_mode == "reactive":
                dyn_parts.append(
                    "[Act Mode: reactive]\n"
                    "直接回应当前请求,保持简洁;如果需要工具,先判断必要性再行动。"
                )
            else:
                plan_text = "\n".join(f"{i}. {step}" for i, step in enumerate(act_plan, 1))
                dyn_parts.append(
                    "[Act Mode: plan_solve]\n"
                    "这是一个多步任务:先调用 `propose_plan` 工具把待办清单提交给用户确认,"
                    "用户认可后再逐步执行(不要跳过确认直接动手改文件)。\n"
                    f"参考计划:\n{plan_text}"
                )
            # 注意:「本轮动态内容」拼在用户消息里,而不是写全局 symbix_client.system_prompt
            # —— 后者是单例上的可变字段,并发会话会互相把 system prompt 读串。
            if dyn_parts:
                user_for_llm = "\n\n".join(dyn_parts) + "\n\n" + user_for_llm

            # native 工具始终可用;use_mcp 仅附带外部 MCP
            if request.use_mcp:
                # MCP 列工具是同步阻塞的(每个 server 最长等 30 秒),丢线程池,
                # 否则一次卡顿会把所有会话的流式输出一起冻住
                mcp_tools = await asyncio.to_thread(tool_registry.get_openai_tools)
            else:
                mcp_tools = tool_registry.native.get_openai_tools()


            steps = []
            tool_calls_raw = None
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
            # token 统计:上游若在 done 里带回真实 usage,从这里开始收集
            last_usage: dict | None = None
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
                system_prompt=stable_prompt,
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
                    if event.get("usage"):
                        last_usage = event["usage"]
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
                system_prompt=stable_prompt,
            )
            cum_tool_tokens = 0
            # token 统计:估算用的 messages 快照(每轮更新)
            usage_msgs = running_msgs

            def _usage_payload() -> dict:
                payload = build_usage_payload(usage_msgs, mcp_tools, full_text, upstream=last_usage)
                # 记入 token_usage.db:一个请求可能有多个 done 出口(await_input/提前返回/
                # 轮次用尽),用 _recorded 保证整轮只记一次
                nonlocal _usage_recorded
                if not _usage_recorded:
                    _usage_recorded = True
                    try:
                        up = payload.get("upstream") or {}
                        usage_store.record(
                            ts=int(_time.time()), session_id=request.session_id, model=model,
                            prompt=payload["prompt"], output=payload["output"],
                            tools=payload["tools"], total=payload["total"],
                            up_prompt=up.get("prompt_tokens"),
                            up_completion=up.get("completion_tokens"),
                            up_total=up.get("total_tokens"),
                            payload=_json.dumps(payload, ensure_ascii=False),
                        )
                    except Exception as e:  # 记录失败不影响对话
                        print(f"[usage] record failed: {e}")
                return payload

            _usage_recorded = False

            # 子 Agent 委派所需的请求级模型参数(不同模型/网关时与主 Agent 保持一致)
            # 子 Agent 可单独配置模型(model_setting 页「子 Agent 模型」),未配置则沿用主模型;
            # api_key / api_base 仍与主模型共用。
            _delegate_ctx = {
                "api_key": api_key,
                "api_base": api_base,
                "model": provider_registry.get_sub_model() or model,
                "session_id": request.session_id,
            }

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

                parallel_claimed: set[int] = set()
                for idx_tc, tc in enumerate(tool_calls_raw):
                    if idx_tc in parallel_claimed:
                        continue
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
                                "system_prompt": stable_prompt,
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
                                # options 带描述/点击行为,前端渲染成选项列表
                                "options": qdata.get("options", []),
                                "context": qdata.get("context", ""),
                                # kind="plan" 时前端渲染成「执行计划确认」卡;
                                # plan 用于用户确认后把待办清单回注给模型
                                "kind": qdata.get("kind", ""),
                                "plan": qdata.get("plan", []),
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
                                "options": qdata.get("options", []),
                                "context": qdata.get("context", ""),
                                "kind": qdata.get("kind", ""),
                                "tool": {"id": tc_id, "name": tc_name},
                            })
                            yield format_sse({"type": "done", "content": full_text, "usage": _usage_payload()})
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
                            # 续跑时重建 messages 要用同一份 system prompt(不读全局单例)
                            "system_prompt": stable_prompt,
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
                        yield format_sse({"type": "done", "content": full_text, "usage": _usage_payload()})
                        # — checkpoint: 本轮被审批拦住,尚未完成 → round 未完待续
                        _emit_round_summary(
                            request.session_id, ckpt_round_id,
                            mem_msg, full_text, last_reasoning,
                            ckpt_tool_count, ckpt_failed,
                            duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                        )
                        return

                    _ctx_set_current(request.session_id, ckpt_round_id)
                    # ── 并行批量:连续的只读工具(读文件/搜索/抓网页)一起跑 ──
                    # 这些工具内部是阻塞 I/O,串行 await 会一个一个等;
                    # 写入/终端/UI/审批/提问/delegate 仍走下面的串行路径。
                    if _is_read_only_parallel_tool(tc_name):
                        _batch = _collect_read_batch(
                            tool_calls_raw, idx_tc, attempted_tool_calls,
                            mcp_tools, request.session_id,
                        )
                    else:
                        _batch = []
                    if len(_batch) > 1:
                        for _j, _btc, _bsig, _ in _batch:
                            attempted_tool_calls.add(_bsig)
                            if _j != idx_tc:
                                parallel_claimed.add(_j)
                        _btc_by_idx = {j: btc for j, btc, _s, _r in _batch}
                        _lvl_by_idx = {j: lvl for j, _b, _s, lvl in _batch}
                        _outs: dict[int, str] = {}
                        async for _j, _out in run_tools_parallel(
                            [(j, btc.get("name", ""), btc.get("arguments", "{}"))
                             for j, btc, _s, _r in _batch]
                        ):
                            _outs[_j] = _out
                            _btc = _btc_by_idx[_j]
                            _bname = _btc.get("name", "")
                            # 完成即发:前端按 tool_call_id 就地回填卡片,不受到达顺序影响
                            yield format_sse({
                                "type": "tool_result",
                                "id": _btc.get("id", ""),
                                "name": _bname,
                                "content": _out,
                            })
                            ckpt_tool_count += 1
                            if _out.startswith("[Error"):
                                ckpt_failed += 1
                                _emit_tool(request.session_id, ckpt_round_id, _bname,
                                           _btc.get("arguments", "{}"), _lvl_by_idx[_j],
                                           True, _out, status="error", error=_out[:200])
                            else:
                                _emit_tool(request.session_id, ckpt_round_id, _bname,
                                           _btc.get("arguments", "{}"), _lvl_by_idx[_j],
                                           True, _out)
                        # steps / round_results 按**原始顺序**补齐,
                        # 保持与 assistant 的 tool_calls 顺序一致(供后续轮拼接与审批快照)。
                        for _j, _btc, _bsig, _ in _batch:
                            _out = _outs.get(_j, "[Error] 工具未返回结果")
                            steps.append({
                                "type": "tool_result",
                                "tool_call_id": _btc.get("id", ""),
                                "name": _btc.get("name", ""),
                                "content": _out,
                            })
                            round_results.append({
                                "tool_call_id": _btc.get("id", ""),
                                "role": "tool",
                                "name": _btc.get("name", ""),
                                "content": _out,
                                "arguments": _btc.get("arguments", "{}"),
                            })
                        continue

                    tool_output = ""
                    async for _kind, _payload in _stream_tool_events(tc_name, tc_args, _delegate_ctx):
                        if _kind == "progress":
                            if isinstance(_payload, dict):
                                yield format_sse({"type": "delegate_progress", "name": tc_name, **_payload})
                        else:
                            tool_output = _payload
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
                symbix_client._build_tool_result_messages(running_msgs, round_results, last_reasoning)
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
                usage_msgs = msgs

                provider = provider_registry.get_active()
                raw_model = model or provider.model
                raw_base = api_base or provider.api_base
                api_key_val = api_key or provider.api_key
                url, ptype, headers, model_name = symbix_client._resolve_endpoint(
                    raw_model, raw_base, api_key_val
                )

                tool_calls_raw = None
                full_text_round = ""
                # 统一走 _open_stream:三条管道都带上「限流/5xx/断线重试」
                async for e in symbix_client._open_stream(
                    url, ptype, headers, model_name, msgs, mcp_tools,
                    caps_model_override=raw_model,
                ):
                    if e["type"] == "stream_reset":
                        full_text_round = ""
                        yield format_sse({"type": "content_reset", "reason": e.get("reason")})
                        continue
                    yield format_sse(_client_event(e))
                    if e["type"] == "delta":
                        full_text_round += e["content"]
                    elif e["type"] == "reasoning":
                        last_reasoning = e.get("content")
                    elif e["type"] == "done":
                        tool_calls_raw = e.get("tool_calls")
                        if e.get("reasoning"):
                            last_reasoning = e.get("reasoning")
                        if e.get("usage"):
                            last_usage = e["usage"]
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
                "usage": _usage_payload(),
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
                # 中断轮也补一条 round 总结点,否则时间线里这一轮只有起点、没有终点
                _emit_round_summary(
                    request.session_id, ckpt_round_id,
                    mem_msg, interrupted_note, last_reasoning,
                    ckpt_tool_count, ckpt_failed,
                    duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                    status="error", error="用户中断",
                )
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
            try:
                _emit_round_summary(
                    request.session_id, ckpt_round_id,
                    mem_msg, full_text, last_reasoning,
                    ckpt_tool_count, ckpt_failed,
                    duration_ms=int((asyncio.get_event_loop().time() - ckpt_start_ts) * 1000),
                    status="error", error=str(e),
                )
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
