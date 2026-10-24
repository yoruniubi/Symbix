"""审批续跑路由:/chat/approve。"""
import asyncio
import time as _time
import uuid
import json as _json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from application.schemas import ApproveRequest
from application.state import (
    memory,
    provider_registry,
    skill_registry,
    symbix_client,
    tool_registry,
    usage_store,
    _pending_approvals,
    _processing_approvals,
    _pending_questions,
    register_session_task,
    unregister_session_task,
)
from application.services.risk_context import classify_for_chat, get_session_trust
from application.services.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
)
from Symbix_sdk.tools.risk_classifier import classify_tool_risk, ToolRiskLevel
from Symbix_sdk.client import build_tool_result_messages
from Symbix_sdk.checkpoint import set_current as _ctx_set_current
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
    _execute_tool,
    _stream_tool_events,
    MAX_CUM_TOOL_TOKENS,
    build_usage_payload,
)

router = APIRouter(tags=["chat"])


@router.get("/chat/pending")
async def chat_pending(session_id: str = ""):
    """查询某会话仍挂着的审批/提问 id。

    前端恢复会话(切回旧对话/重开窗口)时用它对账:localStorage 里的历史消息带着
    早已失效的 approval_id,后端只把挂起态放在内存里,重启就没了。对账后前端把
    过期卡片标成「已失效」,而不是留一个点了必然报错的按钮。
    """
    ids = [
        aid for aid, ctx in _pending_approvals.items()
        if not session_id or ctx.get("session_id") == session_id
    ]
    return {"ids": ids}


@router.post("/chat/approve")
async def chat_approve(req: ApproveRequest, http_request: Request):
    print(f"[APPROVE] Received approval_id={req.approval_id}, pending keys={list(_pending_approvals.keys())}")
    if req.approval_id in _processing_approvals:
        print(f"[APPROVE] approval_id {req.approval_id} is already processing")
        raise HTTPException(status_code=409, detail="approval is already being processed")
    ctx = _pending_approvals.pop(req.approval_id, None)
    if not ctx:
        print(f"[APPROVE] approval_id {req.approval_id} not found in pending")
        # 410 而不是 404:这是「曾经有效但已经失效」(后端重启 / 会话挂起态被清理),
        # 前端要把卡片标成不可续跑并说人话,而不是弹一个 HTTP 404。
        raise HTTPException(
            status_code=410,
            detail="审批已失效:后端重启或该会话的挂起状态已被清理,请直接回复一句话让我继续",
        )

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
    # 子 Agent 委派所需的请求级模型参数(与主 Agent 一致;子 Agent 可单独配模型)
    _delegate_ctx = {
        "api_key": api_key,
        "api_base": api_base,
        "model": provider_registry.get_sub_model() or model,
        "session_id": ctx["session_id"],
    }
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
        # —— 交互型工具(提问)的挂起:用户回答注入为工具结果,不真执行工具。
        is_question = bool(ctx.get("is_question"))
        if is_question:
            _ctx_set_current(ctx["session_id"], ckpt_round_id)
            qinfo = _pending_questions.pop(req.approval_id, {})
            # 用户可能点了建议按钮(默认 approve=true)或取消;取消则以“用户取消”作为回答。
            answer = (req.answer or "").strip() or (qinfo.get("suggestions") or [""])[0] if req.approve else "用户取消提问"
            out = f"[用户回答] {answer}"
            # 计划确认卡:用户认可后把待办清单回注,否则模型看不到自己刚提交过的步骤
            # (工具调用的 arguments 不在续跑上下文里重建)。
            plan_steps = qinfo.get("plan") or []
            if qinfo.get("kind") == "plan" and plan_steps:
                if req.approve:
                    plan_text = "\n".join(
                        f"{i}. {s}" for i, s in enumerate(plan_steps, 1)
                    )
                    out += (
                        "\n[计划已确认,按此待办逐步执行]\n"
                        f"{plan_text}\n"
                        "每完成一步再进入下一步;中途如需变更,用 `propose_plan` 重新确认。"
                    )
                else:
                    out += "\n[用户未认可该计划,请先不要动手,等用户补充要求或改用 `propose_plan` 重新提交]"
            steps.append({
                "type": "tool_result",
                "tool_call_id": pending_tc["id"],
                "name": pending_tc["name"],
                "content": out,
                "approved": req.approve,
                "question_answer": True,
            })
            ckpt_tool_count += 1
            # 这条工具调用是「提问占位」,其结果是用户回答(不再真正执行工具)
            _emit_tool(ctx["session_id"], ckpt_round_id, pending_tc["name"], pending_tc.get("arguments"),
                       ctx.get("risk_level", "medium"), True, out,
                       status="ok")
            # 直接跳到工具结果累积;不再走下面的 execute
        elif req.approve:
            _ctx_set_current(ctx["session_id"], ckpt_round_id)
            # — 会话信任:用户批准写入后,记下 write 通道 grant(exec/delete/network 不记)
            _approve_risk = ctx.get("risk")
            if _approve_risk is not None and _approve_risk.channel == "write":
                try:
                    _st = get_session_trust(ctx["session_id"])
                    _st.grant(_approve_risk.channel, server_id=_approve_risk.server_id)
                except Exception:
                    pass
            out = await _execute_tool(pending_tc["name"], pending_tc["arguments"], _delegate_ctx)
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
                _emit_tool(ctx["session_id"], ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
                           ctx.get("risk_level", "medium"), True, out,
                           status="error", error=out[:200])
            else:
                _emit_tool(ctx["session_id"], ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
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
            _emit_tool(ctx["session_id"], ckpt_round_id, pending_tc["name"], pending_tc["arguments"],
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

            # 交互型工具:不与其他审批同批执行 —— 注入提示让模型单独提问
            if _is_interaction_tool(tc["name"]):
                r_out = (
                    f"[System] 工具 `{tc['name']}` 需单独向用户提问,不能与本次审批同时执行。"
                    "请在完成当前流程后再单独提问。"
                )
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
                continue

            _risk = classify_tool_risk(tc["name"], args)
            risk_level = _risk.level
            if risk_level != ToolRiskLevel.SAFE:
                # 如果剩余的 tool_calls 中也有需要审批的工具，应该阻挡
                r_out = f"[安全策略] 本轮还包含审批工具 '{tc['name']}'，但一次只能审批一个。请单独确认后再继续。"
            else:
                _ctx_set_current(ctx["session_id"], ckpt_round_id)
                r_out = await _execute_tool(tc["name"], tc["arguments"], _delegate_ctx)
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
            # token 用量收口:多个 done 出口共用,整轮只记一次(与 stream.py 同一套路)
            _usage_recorded = False

            def _usage_payload() -> dict:
                nonlocal _usage_recorded
                payload = build_usage_payload(running_msgs, mcp_tools, full_text, upstream=last_usage)
                if not _usage_recorded:
                    _usage_recorded = True
                    try:
                        up = payload.get("upstream") or {}
                        usage_store.record(
                            ts=int(_time.time()), session_id=session_id,
                            model=provider_registry.get_active().model,
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

            # checkpoint 计数袭用外层 chat_approve 的局部变量:嵌套函数内对它们做 += 必须显式 nonlocal,
            # 否则 Python 会按本函数局部赋值导致 UnboundLocalError("cannot access local variable ...").
            nonlocal ckpt_tool_count, ckpt_failed, ckpt_start_ts
            # 注册本会话进行中任务:删除对话时可一并取消,终止 chat/action。
            _gen_task = asyncio.current_task()
            register_session_task(session_id, _gen_task)
            try:
                # 先把已执行的步骤发给前端
                yield format_sse({"type": "steps", "steps": steps})

                # 拒绝审批时补发 tool_result 事件,让前端立刻把对应 step 标记为 rejected,
                # 避免残留 awaiting_approval 的 step-card(旧 step 被后续同名工具误标)。
                if not req.approve:
                    pending = ctx["pending_tc"]
                    yield format_sse({
                        "type": "tool_result",
                        "id": pending["id"],
                        "name": pending["name"],
                        "content": f"[用户拒绝执行工具 {pending['name']}]",
                        "approved": False,
                    })

                # 构建含 tool_results 的 messages
                # 基底 = history + 审批前已执行工具链(若有),
                # 使续跑模型能看到审批前已经跑过的 SAFE 工具(list_files 等),不再"失忆"重列。
                msgs = symbix_client._build_messages(
                    history,
                    user_input,
                    registry=skill_registry,
                    tools=mcp_tools,
                    image_parts=None,
                    # 显式传本轮 system prompt(优先用挂起时快照的,否则用前端上送),
                    # 不碰全局 symbix_client.system_prompt → 并发会话不会互串。
                    system_prompt=ctx.get("system_prompt") or req.system_prompt or None,
                )
                tool_chain_msgs = ctx.get("tool_chain_msgs") or []
                if tool_chain_msgs:
                    msgs.extend(tool_chain_msgs)
                # 本轮 assistant(tool_calls) + tool 结果:带上本轮 reasoning
                # (思考模式上游要求回传 reasoning_content,否则续跑 400)
                build_tool_result_messages(msgs, tool_results, reasoning=last_reasoning)
                # 首轮消息即作为后续累积基底,后续轮工具结果在此之上追加。
                running_msgs = msgs
                _assert_tool_pairing(running_msgs, strict=False)

                full_text = ""
                tool_calls_raw = None
                _batcher = _DeltaBatcher()
                # token 统计:上游若在 done 里带回真实 usage,从这里收集(与 /chat/stream 同口径)
                last_usage: dict | None = None

                provider = provider_registry.get_active()
                raw_model = model or provider.model
                raw_base = api_base or provider.api_base
                api_key_val = api_key or provider.api_key
                url, ptype, headers, model_name = symbix_client._resolve_endpoint(
                    raw_model, raw_base, api_key_val
                )

                # 第一轮流式输出（审批后继续生成）;统一走 _open_stream 以享用重试外壳
                async for e in symbix_client._open_stream(
                    url, ptype, headers, model_name, msgs, mcp_tools,
                    caps_model_override=raw_model,
                ):
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
                        if e.get("usage"):
                            last_usage = e["usage"]
                        if e.get("error"):
                            print(f"[_stream_approve] 内容不完整: {e['error']}")

                flushed = _batcher.flush()
                if flushed is not None:
                    yield flushed

                # 后续 tool_calls 循环(复用 chat_stream 主循环逻辑)
                round_count_local = ctx["round_count"]
                # 跨审批延续去重集合:让嵌套/后续审批仍记得前面已调用过的 (name, args)。
                attempted = set(ctx.get("attempted_tool_calls") or ())
                # 频次检测:同一工具+相同参数(签名)调用超过阈值才触发(不同参数不误伤)
                name_counts_local: dict[tuple, int] = dict(ctx.get("tool_name_counts") or {})
                LOCAL_WRITE_TOOLS = {"edit_file", "write_to_file", "replace_in_file",
                                     "delete_file", "create_skill", "run_command",
                                     "open_terminal"}
                MAX_WRITE_NAME = 3
                # 防上下文无限增长:随每轮工具结果累计估算 token。
                cum_tool_tokens = 0
                # 本轮连续"重复拦截"注入合成结果的次数,防模型无视提示死循环。
                synthetic_count = 0
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
                    for idx_tc, tc in enumerate(tool_calls_raw):
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
                            err = (
                                f"[System] 工具 `{tc_name}` 在本轮已用相同参数调用过,已阻止重复执行。"
                                "请基于上文的工具结果继续推进;若确实需要最新状态/重跑,"
                                "请更换参数或向用户说明理由,不要原样重试。"
                            )
                            steps.append({"type": "tool_result", "tool_call_id": tc_id, "name": tc_name, "content": err, "synthetic": True})
                            yield format_sse({"type": "tool_result", "id": tc_id, "name": tc_name, "content": err})
                            # 合成结果同样进入 new_results,让模型看到"已被拦"。
                            new_results.append({"tool_call_id": tc_id, "role": "tool", "name": tc_name, "content": err, "arguments": tc_args})
                            synthetic_count += 1
                            # 模型连续两次无视重复提示 → 直接结束循环收尾。
                            if synthetic_count >= 2:
                                tool_calls_raw = None
                                full_text = full_text or err
                                break
                            continue
                        attempted.add(sig)

                        # 频次检测:同一工具+相同参数(签名)反复调用 → 强制终止循环,要求总结
                        if tc_name in LOCAL_WRITE_TOOLS:
                            name_counts_local[sig] = name_counts_local.get(sig, 0) + 1
                            if name_counts_local[sig] > MAX_WRITE_NAME:
                                stop_hint = (
                                    f"[System] 工具 `{tc_name}` 已用相同参数被调用 "
                                    f"{name_counts_local[sig] - 1} 次。看起来你在重复调用同一工具。"
                                    "请立即停下来,向用户总结已完成的工作,不要再调用任何写入工具。"
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

                        _risk, _needs_approval, _ = classify_for_chat(
                            tc_name, tc_args, mcp_tools, session_id,
                        )
                        risk_level, risk_reason = _risk.level, _risk.reason

                        # 交互型工具(ask_clarifying_question):挂起等用户回答(同主循环)
                        if _is_interaction_tool(tc_name):
                            tool_output = tool_registry.execute(tc_name, tc_args)
                            if not isinstance(tool_output, str):
                                tool_output = _json.dumps(tool_output, ensure_ascii=False)
                            qdata = _parse_interaction_request(tool_output)
                            if qdata:
                                approval_id = str(uuid.uuid4())
                                _pending_approvals[approval_id] = {
                                    "session_id": session_id,
                                    "user_input": user_input,
                                    "history": history,
                                    # 嵌套提问也要带回本轮 system prompt 快照(续跑显式传参)
                                    "system_prompt": ctx.get("system_prompt") or req.system_prompt or "",
                                    "tool_chain_msgs": _steps_to_tool_messages(steps),
                                    "attempted_tool_calls": attempted,
                                    "tool_name_counts": name_counts_local,
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
                                    "is_question": True,
                                    "pending_tc": {"id": tc_id, "name": tc_name, "arguments": tc_args},
                                    "ckpt_round_id": ctx.get("ckpt_round_id", ckpt_round_id),
                                    "remaining_tcs": [],
                                    "risk_level": risk_level,
                                    "risk_reason": risk_reason,
                                    "risk": _risk,
                                }
                                _pending_questions[approval_id] = {
                                    "question": qdata.get("question", ""),
                                    "suggestions": qdata.get("suggestions", []),
                                    "options": qdata.get("options", []),
                                    "context": qdata.get("context", ""),
                                    "kind": qdata.get("kind", ""),
                                    "plan": qdata.get("plan", []),
                                }
                                ckpt_tool_count += 1
                                _emit_tool(session_id, ckpt_round_id, tc_name, tc_args,
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
                                yield format_sse({
                                    "type": "done",
                                    "content": full_text,
                                    "usage": _usage_payload(),
                                })
                                return

                        if _needs_approval:
                            approval_id = str(uuid.uuid4())
                            _pending_approvals[approval_id] = {
                                "session_id": session_id,
                                "user_input": user_input,
                                "history": history,
                                "system_prompt": ctx.get("system_prompt") or req.system_prompt or "",
                                # 嵌套审批也要带上前置已执行工具链 + 去重集合,
                                # 否则二次审批续跑又会对前面的工具"失忆"。
                                "tool_chain_msgs": _steps_to_tool_messages(steps),
                                "attempted_tool_calls": attempted,
                                "tool_name_counts": name_counts_local,
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
                                # 只保留尚未执行(在当前审批工具之后)的调用,避免二次执行。
                                "remaining_tcs": [{"id": r["id"], "name": r["name"], "arguments": r.get("arguments", "{}")} for r in tool_calls_raw[idx_tc + 1:]],
                                "risk_level": risk_level,
                                "risk_reason": risk_reason,
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
                            yield format_sse({
                                "type": "done",
                                "content": full_text,
                                "usage": _usage_payload(),
                            })
                            return

                        _ctx_set_current(session_id, ckpt_round_id)
                        out = ""
                        # 异步工具(delegate_task/delegate_tasks)边跑边把进度推成 SSE
                        async for _kind, _payload in _stream_tool_events(tc_name, tc_args, _delegate_ctx):
                            if _kind == "progress":
                                if isinstance(_payload, dict):
                                    yield format_sse({"type": "delegate_progress", "name": tc_name, **_payload})
                            else:
                                out = _payload
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

                    # 后续轮同样增量累积到 running_msgs,不再从 history 重建。
                    symbix_client._build_tool_result_messages(running_msgs, new_results, last_reasoning)
                    _assert_tool_pairing(running_msgs, strict=False)
                    cum_tool_tokens += sum(
                        _estimate_tool_tokens(str(tr.get("content", ""))) for tr in new_results
                    )
                    if cum_tool_tokens > MAX_CUM_TOOL_TOKENS:
                        print(f"[approve] 工具结果累积超限({cum_tool_tokens} tok),终止工具循环")
                        tool_calls_raw = None
                        full_text = full_text or "[已完成较多工具调用,为避免上下文过长提前收尾。]"
                        break
                    msgs = running_msgs

                    tool_calls_raw = None
                    full_text_round = ""
                    _batcher2 = _DeltaBatcher()
                    # 后续轮同样走 _open_stream(重试外壳)
                    async for e in symbix_client._open_stream(
                        url, ptype, headers, model_name, msgs, mcp_tools,
                        caps_model_override=raw_model,
                    ):
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
                            if e.get("usage"):
                                last_usage = e["usage"]
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
                yield format_sse({
                    "type": "done",
                    "content": full_text,
                    "act_mode": act_mode,
                    "act_plan": act_plan,
                    "usage": _usage_payload(),
                })
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
                yield "data: [DONE]\n\n"
            finally:
                _processing_approvals.discard(req.approval_id)
                unregister_session_task(session_id, _gen_task)

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
