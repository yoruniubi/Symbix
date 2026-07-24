"""对话相关路由：/chat, /chat/stream, /chat/approve, /upload, /parse_file, /history"""
import asyncio
import uuid
import json as _json
from fastapi import APIRouter, HTTPException, File, UploadFile, Form
from fastapi.responses import StreamingResponse

from application.models import ChatRequest, ChatResponse, ApproveRequest
from application.state import (
    memory,
    provider_registry,
    skill_registry,
    symbix_client,
    tool_registry,
    APPROVAL_TOOLS,
    _pending_approvals,
)
from application.memory_ops import (
    maybe_compress_session,
    maybe_extract_memories,
    format_sse,
    build_system_prompt,
)

router = APIRouter(tags=["chat"])
def _prepare_user_message(request: ChatRequest) -> tuple[str, list[dict], list[dict]]:
    """解析 attachments 并注入用户消息；返回 (enriched_text, parsed_list, image_parts)。"""
    from Symbix_sdk.tools.file_pipeline import inject_attachments_into_message

    atts = []
    for a in request.attachments or []:
        if hasattr(a, "model_dump"):
            atts.append(a.model_dump())
        elif isinstance(a, dict):
            atts.append(a)
        else:
            atts.append(dict(a))
    return inject_attachments_into_message(request.message, atts)


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
async def chat(request: ChatRequest):
    try:
        api_key = request.api_key or provider_registry.get_active().api_key
        api_base = request.api_base or provider_registry.get_active().api_base
        model = request.model or provider_registry.get_active().model

        user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
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

        # 注入 RAG 记忆到 system prompt
        use_mem = getattr(request, "use_memory", True)
        enriched_prompt = build_system_prompt(
            base=request.system_prompt,
            use_memory=use_mem,
            user_query=mem_msg,
            session_id=request.session_id,
        )
        symbix_client.system_prompt = enriched_prompt

        mcp_tools = None
        if request.use_mcp:
            mcp_tools = tool_registry.get_openai_tools()

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

        max_tool_rounds = 5
        round_count = 0
        while response.get("tool_calls") and round_count < max_tool_rounds:
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
                if fn.name in APPROVAL_TOOLS:
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
                        "pending_tc": {"id": tc.id, "name": fn.name, "arguments": fn.arguments},
                        "remaining_tcs": [
                            {"id": r.id, "name": r.function.name, "arguments": r.function.arguments}
                            for r in response["tool_calls"]
                        ],
                    }

                    return {
                        "status": "pending_approval",
                        "approval_id": approval_id,
                        "session_id": request.session_id,
                        "content": "",
                        "reasoning": last_reasoning,
                        "steps": steps,
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

        asyncio.create_task(maybe_compress_session(
            request.session_id, api_key, api_base, model))
        asyncio.create_task(maybe_extract_memories(
            request.session_id, api_key, api_base, model))

        return ChatResponse(
            content=assistant_content,
            session_id=request.session_id,
            reasoning=last_reasoning,
            steps=steps,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/approve")
async def chat_approve(req: ApproveRequest):
    ctx = _pending_approvals.pop(req.approval_id, None)
    if req.system_prompt:
        symbix_client.system_prompt = req.system_prompt
    if not ctx:
        raise HTTPException(status_code=404, detail="approval not found")

    steps = ctx["steps"]
    user_input = ctx["user_input"]
    history = ctx["history"]
    mcp_tools = ctx["mcp_tools"]
    api_key = ctx["api_key"]
    api_base = ctx["api_base"]
    model = ctx["model"]
    round_count = ctx["round_count"]
    pending_tc = ctx["pending_tc"]
    remaining_tcs = ctx["remaining_tcs"]

    tool_results = []
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
    else:
        out = f"[用户拒绝执行工具 {pending_tc['name']}]"
        steps.append({
            "type": "tool_result",
            "tool_call_id": pending_tc["id"],
            "name": pending_tc["name"],
            "content": out,
            "approved": False,
        })
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
    max_tool_rounds = 5
    response = await symbix_client.chat_with_tool_results(
        user_input=user_input,
        history=history,
        registry=skill_registry,
        tools=mcp_tools,
        tool_results=tool_results,
        override_api_key=api_key,
        override_api_base=api_base,
        override_model=model,
    )
    last_reasoning = response.get("reasoning")

    while response.get("tool_calls") and round_count < max_tool_rounds:
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
            if fn.name in APPROVAL_TOOLS:
                approval_id = str(uuid.uuid4())
                _pending_approvals[approval_id] = {
                    "session_id": ctx["session_id"],
                    "user_input": user_input,
                    "history": history,
                    "mcp_tools": mcp_tools,
                    "api_key": api_key,
                    "api_base": api_base,
                    "model": model,
                    "steps": steps,
                    "last_reasoning": last_reasoning,
                    "round_count": round_count,
                    "pending_tc": {"id": tc.id, "name": fn.name, "arguments": fn.arguments},
                    "remaining_tcs": [
                        {"id": r.id, "name": r.function.name, "arguments": r.function.arguments}
                        for r in response["tool_calls"]
                    ],
                }
                return {
                    "status": "pending_approval",
                    "approval_id": approval_id,
                    "session_id": ctx["session_id"],
                    "content": "",
                    "reasoning": last_reasoning,
                    "steps": steps,
                    "pending_tool": {
                        "tool_call_id": tc.id,
                        "name": fn.name,
                        "arguments": fn.arguments,
                    },
                }
            out = tool_registry.execute(fn.name, fn.arguments)
            if not isinstance(out, str):
                out = _json.dumps(out, ensure_ascii=False)
            tool_results.append({
                "tool_call_id": tc.id,
                "role": "tool",
                "name": fn.name,
                "content": out,
                "arguments": fn.arguments if hasattr(fn, "arguments") else "{}",
            })
            steps.append({
                "type": "tool_result",
                "tool_call_id": tc.id,
                "name": fn.name,
                "content": out,
            })
        response = await symbix_client.chat_with_tool_results(
            user_input=user_input,
            history=history,
            registry=skill_registry,
            tools=mcp_tools,
            tool_results=tool_results,
            override_api_key=api_key,
            override_api_base=api_base,
            override_model=model,
        )
        last_reasoning = response.get("reasoning")

    assistant_content = response["content"]
    memory.add(ctx["session_id"], "assistant", assistant_content)

    sid = ctx["session_id"]
    key = ctx.get("api_key", "")
    base = ctx.get("api_base", "")
    mdl = ctx.get("model", "")
    asyncio.create_task(maybe_compress_session(sid, key, base, mdl))
    asyncio.create_task(maybe_extract_memories(sid, key, base, mdl))

    return {
        "status": "ok",
        "content": assistant_content,
        "session_id": ctx["session_id"],
        "reasoning": last_reasoning,
        "steps": steps,
    }


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """AI 流式对话接口 (SSE) - 支持完整的 tool_calls 循环和审批"""

    async def generate():
        try:
            api_key = request.api_key
            api_base = request.api_base
            model = request.model or provider_registry.get_active().model

            user_for_llm, parsed_atts, image_parts = _prepare_user_message(request)
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

            # 注入 RAG 记忆到 system prompt
            use_mem = getattr(request, "use_memory", True)
            enriched_prompt = build_system_prompt(
                base=request.system_prompt,
                use_memory=use_mem,
                user_query=mem_msg,
                session_id=request.session_id,
            )
            symbix_client.system_prompt = enriched_prompt

            mcp_tools = None
            if request.use_mcp:
                mcp_tools = tool_registry.get_openai_tools()

            steps = []
            full_text = ""
            tool_calls_raw = None

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
                yield format_sse(event)

                if event["type"] == "delta":
                    full_text += event["content"]
                elif event["type"] == "tool_call":
                    pass
                elif event["type"] == "done":
                    full_text = event.get("content") or full_text
                    tool_calls_raw = event.get("tool_calls")

            max_rounds = 5
            round_count = 0
            last_reasoning = None

            while tool_calls_raw and round_count < max_rounds:
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

                    if tc_name in APPROVAL_TOOLS:
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
                            "pending_tc": {
                                "id": tc_id,
                                "name": tc_name,
                                "arguments": tc_args,
                            },
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
                        })
                        yield format_sse({"type": "done", "content": full_text})
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
                        "content": tool_output[:200] + ("..." if len(tool_output) > 200 else ""),
                    })

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
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                elif ptype == "gemini":
                    async for e in symbix_client._stream_gemini(
                        url, headers, msgs, mcp_tools
                    ):
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                else:
                    async for e in symbix_client._stream_openai_compat(
                        url, headers, model_name, msgs, mcp_tools
                    ):
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "reasoning":
                            last_reasoning = e.get("content")
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                            if e.get("reasoning"):
                                last_reasoning = e.get("reasoning")

                if full_text_round:
                    full_text = full_text_round

            memory.add(request.session_id, "assistant", full_text)
            yield format_sse({"type": "done", "content": full_text})
            yield "data: [DONE]\n\n"

            asyncio.create_task(maybe_compress_session(
                request.session_id, api_key or "", api_base or "", model or ""))
            asyncio.create_task(maybe_extract_memories(
                request.session_id, api_key or "", api_base or "", model or ""))

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