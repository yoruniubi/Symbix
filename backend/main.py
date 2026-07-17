"""
Symbix Backend - FastAPI Server
提供 AI 对话、Skill 管理和 MCP 支持的 REST API
"""
import uvicorn
import asyncio
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Any
from Symbix_sdk.client import SymbixClient
from Symbix_sdk.providers import ProviderRegistry
from Symbix_sdk.memory import ConversationMemory
from Symbix_sdk.config.mcp_config import McpConfig
from Symbix_sdk.mcp.connector import McpServerManager
from Symbix_sdk.tools.registry import ToolRegistry
from Symbix_sdk.skill.registry import SkillRegistry
from Symbix_sdk.mcp.installer import McpInstaller
import os
import traceback
import json as _json
# ============ FastAPI App ============
app = FastAPI(title="Symbix API", version="0.1.0")

# ============ CORS 跨域支持 ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 初始化核心组件 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

memory = ConversationMemory(
    db_path=os.path.join(BASE_DIR, "Symbix_sdk", "memory", "memory.db")
)
provider_registry = ProviderRegistry(
    config_path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "providers.json")
)
skill_registry = SkillRegistry(
    skills_dir=os.path.join(BASE_DIR, "Symbix_sdk", "skill", "installed_skill")
)

try:
    _ = provider_registry.get_active()
except RuntimeError:
    provider_registry.add("default", "gpt-4o-mini")

symbix_client = SymbixClient(registry=provider_registry)

# ============ MCP 配置与工具包 ============
mcp_config = McpConfig(
    path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "mcp_config.json")
)
mcp_installer = McpInstaller(config_path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "mcp_config.json"))

class InstallNpmRequest(BaseModel):
    package_name: str
    server_id: str
    args: list[str] = []

# MCP Server 管理器
mcp_manager = McpServerManager()

# 初始化 MCP servers（从配置文件启动，兼容本地 stdio 与远程 URL）
def initialize_mcp_servers():
    """从配置文件启动所有 MCP servers"""
    servers = mcp_config.get_servers()
    for server_id, config in servers.items():
        try:
            success = mcp_manager.add_from_config(server_id, config or {})
            if success:
                print(f"[MCP] Started server: {server_id}")
            else:
                print(f"[MCP] Failed to start server: {server_id}")
        except Exception as e:
            print(f"[MCP] Failed to start server '{server_id}': {e}")

# 启动时初始化 MCP servers
initialize_mcp_servers()

# 使用 ToolRegistry 统一管理 native + mcp 工具
tool_registry = ToolRegistry(mcp_manager=mcp_manager)
# 把已加载的 skill 注册为可调用工具（出现在工具列表中）
tool_registry.set_skill_registry(skill_registry)


# ============ 请求模型 ============
class AttachmentMeta(BaseModel):
    """上传接口返回的附件元数据，发送聊天时回传 path。"""
    path: str = ""
    filename: str = ""
    name: str = ""
    mime: str = ""
    type: str = ""
    content: str = ""  # 可选：前端直接给文本内容
    size: int = 0


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []
    system_prompt: str = ""
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    use_mcp: bool = False
    attachments: list[AttachmentMeta] = []


class ChatResponse(BaseModel):
    content: str
    session_id: str
    reasoning: str = None
    steps: list = []


# 需要用户确认的工具白名单（操作类工具）
APPROVAL_TOOLS = {"edit_file", "write_to_file", "replace_in_file", "delete_file", "run_command", "open_terminal", "create_skill"}

# 内存中的待审批任务：approval_id -> {event, decision, info}
_pending_approvals: dict[str, dict] = {}


class ProviderAddRequest(BaseModel):
    name: str
    model: str
    api_key: str = None
    api_base: str = None


class MessageItem(BaseModel):
    role: str
    content: str


class SessionPayload(BaseModel):
    session_id: str = ""
    title: str = "新对话"
    history: List[MessageItem] = []


class DeleteMarkdownRequest(BaseModel):
    session_id: str = ""
    title: str = ""


class RenameSessionRequest(BaseModel):
    session_id: str
    title: str
    old_title: str = ""


class GenerateTitleRequest(BaseModel):
    session_id: str = ""
    context: str = ""


# ============ 上下文压缩 & 用户画像 ============

# 触发压缩的消息阈值（超过后压缩旧消息）
COMPRESS_THRESHOLD = 16
# 压缩后保留的最近消息数
RECENT_KEEP = 12


async def maybe_compress_session(session_id: str, api_key: str = "", api_base: str = "", model: str = ""):
    """若消息数超过阈值，对旧消息做阶段性摘要并写入 session_summaries"""
    total = memory.count_messages(session_id)
    if total < COMPRESS_THRESHOLD:
        return

    existing = memory.get_summary(session_id)
    covered = existing["covered_until_id"] if existing else 0

    # 取尚未被摘要覆盖的旧消息（排除最近 RECENT_KEEP 条）
    all_msgs = memory.get_history_with_ids(session_id, limit=total)
    if len(all_msgs) <= RECENT_KEEP:
        return

    old_msgs = [m for m in all_msgs[:-RECENT_KEEP] if m["id"] > covered]
    if len(old_msgs) < 4:
        return  # 新消息不够，暂不压缩

    dialogue = "\n".join(
        f"{m['role']}: {m['content'][:300]}" for m in old_msgs
    )
    prev_summary = existing["summary"] if existing else ""
    prompt = (
        "请将以下对话内容压缩为简洁的中文摘要（200字以内），"
        "保留关键事实、结论、用户意图与未完成事项。"
        "只输出摘要正文，不要标题或解释。\n\n"
    )
    if prev_summary:
        prompt += f"【已有摘要】\n{prev_summary}\n\n"
    prompt += f"【需压缩的新对话】\n{dialogue}"

    try:
        result = await symbix_client.chat(
            user_input=prompt,
            history=[],
            registry=skill_registry,
            tools=None,
            override_api_key=api_key or None,
            override_api_base=api_base or None,
            override_model=model or None,
        )
        summary = (result.get("content") or "").strip()
        if summary:
            covered_until = old_msgs[-1]["id"]
            memory.set_summary(session_id, summary, covered_until)
            print(f"[Memory] Compressed session {session_id[:8]}… until id={covered_until}")
    except Exception as e:
        print(f"[Memory] Compress failed: {e}")


async def maybe_extract_profile(session_id: str, user_msg: str, assistant_msg: str = "",
                                api_key: str = "", api_base: str = "", model: str = ""):
    """从本轮对话中提取用户画像事实（职业、项目、偏好等），写入 user_profile"""
    # 只在用户消息较长时才触发，避免每轮都调模型
    if len(user_msg) < 20:
        return

    existing = memory.get_profile()
    existing_text = "\n".join(f"- {k}: {v}" for k, v in existing.items()) if existing else "（暂无）"

    prompt = (
        "从以下对话中提取关于用户的长期事实（职业、公司、项目、技术栈、偏好、目标等）。\n"
        "只输出 JSON 对象，key 为中文短标签，value 为简短描述。\n"
        "如果没有新的可提取事实，返回空对象 {}。\n"
        "不要编造，不要输出 JSON 以外的内容。\n\n"
        f"【已有画像】\n{existing_text}\n\n"
        f"【用户】{user_msg[:500]}\n"
        f"【助手】{(assistant_msg or '')[:300]}"
    )
    try:
        result = await symbix_client.chat(
            user_input=prompt,
            history=[],
            registry=skill_registry,
            tools=None,
            override_api_key=api_key or None,
            override_api_base=api_base or None,
            override_model=model or None,
        )
        raw = (result.get("content") or "").strip()
        # 尝试提取 JSON
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            facts = _json.loads(raw[start:end + 1])
            if isinstance(facts, dict) and facts:
                # 过滤空值
                clean = {str(k): str(v) for k, v in facts.items() if k and v}
                if clean:
                    memory.set_profile_facts(clean)
                    print(f"[Memory] Profile updated: {list(clean.keys())}")
    except Exception as e:
        print(f"[Memory] Profile extract failed: {e}")


def build_system_prompt(base: str = "") -> str:
    """把用户画像拼进 system_prompt"""
    profile_text = memory.get_profile_prompt()
    if not profile_text:
        return base or ""
    if base:
        return f"{base}\n\n{profile_text}"
    return profile_text


# ============ API 路由 ============

@app.get("/")
async def root():
    """根路径 - API 状态检查"""
    return {
        "status": "ok",
        "service": "Symbix API",
        "version": "0.1.0",
    }


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


@app.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    session_id: str = Form("default"),
):
    """上传一个或多个附件到 uploads/{session_id}/，返回可写入 ChatRequest.attachments 的元数据。"""
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
            # 预解析摘要（不内嵌大图 base64，聊天时再完整解析）
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


@app.post("/parse_file")
async def parse_file_api(body: dict):
    """按路径解析已上传/工作区内文件。body: {path, max_chars?}"""
    from Symbix_sdk.tools.file_pipeline import parse_file_path

    path = (body or {}).get("path") or (body or {}).get("file_path") or ""
    max_chars = int((body or {}).get("max_chars") or 50000)
    if not path:
        raise HTTPException(status_code=400, detail="path 不能为空")
    return parse_file_path(path, max_chars=max_chars, include_image_base64=False)



@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        # 直接用请求里的配置，不改 provider_registry
        api_key = request.api_key or provider_registry.get_active().api_key
        api_base = request.api_base or provider_registry.get_active().api_base
        model = request.model or provider_registry.get_active().model

        # 附件解析注入（LLM 用 enriched；记忆存原始 message + 文件名提示）
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
        symbix_client.system_prompt = request.system_prompt

        # 决定是否传入 tools（native + mcp 统一由 ToolRegistry 管理）
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
                        "pending_tool": {"tool_call_id": tc.id, "name": fn.name, "arguments": fn.arguments},
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

        # ── 后台异步：上下文压缩 & 用户画像 ──
        asyncio.create_task(maybe_compress_session(
            request.session_id, api_key, api_base, model))
        asyncio.create_task(maybe_extract_profile(
            request.session_id, mem_msg, assistant_content, api_key, api_base, model))


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


class ApproveRequest(BaseModel):
    approval_id: str
    approve: bool
    session_id: str = "default"
    system_prompt: str = ""
    api_key: str = ""
    api_base: str = ""
    model: str = ""


@app.post("/chat/approve")
async def chat_approve(req: ApproveRequest):
    ctx = _pending_approvals.pop(req.approval_id, None)
    # 注入前端传来的 system_prompt
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
                    "pending_tool": {"tool_call_id": tc.id, "name": fn.name, "arguments": fn.arguments},
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
            steps.append({"type": "tool_result", "tool_call_id": tc.id, "name": fn.name, "content": out})
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

    # 后台异步压缩 + 画像
    sid = ctx["session_id"]
    user_msg = ctx["user_input"]
    key = ctx.get("api_key", "")
    base = ctx.get("api_base", "")
    mdl = ctx.get("model", "")
    asyncio.create_task(maybe_compress_session(sid, key, base, mdl))
    asyncio.create_task(maybe_extract_profile(sid, user_msg, assistant_content, key, base, mdl))

    return {
        "status": "ok",
        "content": assistant_content,
        "session_id": ctx["session_id"],
        "reasoning": last_reasoning,
        "steps": steps,
    }


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """AI 流式对话接口 (SSE) - 支持完整的 tool_calls 循环和审批"""
    from fastapi.responses import StreamingResponse

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
            symbix_client.system_prompt = request.system_prompt

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

            # ── 第一轮流式 ──────────────────────────────────
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
                    pass  # 分片在 done 中整合
                elif event["type"] == "done":
                    full_text = event.get("content") or full_text
                    tool_calls_raw = event.get("tool_calls")

            # ── 工具调用循环 ────────────────────────────────
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

                    # 审批检查
                    if tc_name in APPROVAL_TOOLS:
                        approval_id = str(uuid.uuid4())
                        # 保存上下文
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
                            "tool_calls_remaining": [
                                r for r in tool_calls_raw if r["id"] != tc_id
                            ],
                        }

                        yield format_sse({
                            "type": "await_approval",
                            "approval_id": approval_id,
                            "tool": {"id": tc_id, "name": tc_name, "arguments": tc_args},
                        })
                        yield format_sse({"type": "done", "content": full_text})
                        return  # 等待审批

                    # 执行工具
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

                # 回传工具结果继续流式
                tool_results = [
                    {"tool_call_id": t["id"], "role": "tool", "name": t["name"],
                     "content": steps[-len(tool_calls_raw)+i]["content"]
                     if i < len(steps) and steps[-len(tool_calls_raw)+i]["type"] == "tool_result"
                     else "{}", "arguments": t.get("arguments", "{}")}
                    for i, t in enumerate(tool_calls_raw)
                ]

                # 构建带 tool 结果的消息序列回传（保留 image_parts，避免多轮丢图）
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
                        {"id": t["id"], "type": "function",
                         "function": {"name": t["name"], "arguments": t.get("arguments", "{}")}}
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

                # 重新流式
                provider = provider_registry.get_active()
                raw_model = model or provider.model
                raw_base = api_base or provider.api_base
                api_key_val = api_key or provider.api_key
                url, ptype, headers, model_name = symbix_client._resolve_endpoint(raw_model, raw_base, api_key_val)

                tool_calls_raw = None
                full_text_round = ""
                if ptype == "anthropic":
                    async for e in symbix_client._stream_anthropic(url, headers, model_name, msgs, mcp_tools):
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                elif ptype == "gemini":
                    async for e in symbix_client._stream_gemini(url, headers, msgs, mcp_tools):
                        yield format_sse(e)
                        if e["type"] == "delta":
                            full_text_round += e["content"]
                        elif e["type"] == "done":
                            tool_calls_raw = e.get("tool_calls")
                else:
                    async for e in symbix_client._stream_openai_compat(url, headers, model_name, msgs, mcp_tools):
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

            # 后台异步压缩 + 画像
            asyncio.create_task(maybe_compress_session(
                request.session_id, api_key or "", api_base or "", model or ""))
            asyncio.create_task(maybe_extract_profile(
                request.session_id, mem_msg, full_text, api_key or "", api_base or "", model or ""))


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


# ─── SSE 格式化工具函数 ──────────────────────────────────────
def format_sse(event: dict) -> str:
    """把事件 dict 转成 SSE 文本"""
    event_type = event.get("type", "message")
    payload = _json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@app.get("/history/{session_id}")
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


# ============ 用户画像 ============

@app.get("/api/profile")
async def get_user_profile():
    """获取当前用户画像"""
    return {"profile": memory.get_profile()}


@app.post("/api/profile")
async def update_user_profile(facts: dict):
    """手动更新用户画像（部分覆盖）"""
    if not isinstance(facts, dict):
        raise HTTPException(status_code=400, detail="需要 JSON 对象")
    memory.set_profile_facts({str(k): str(v) for k, v in facts.items()})
    return {"status": "ok", "profile": memory.get_profile()}


@app.delete("/api/profile/{key}")
async def delete_profile_key(key: str):
    """删除一条画像事实"""
    memory.delete_profile_fact(key)
    return {"status": "ok", "profile": memory.get_profile()}


# ============ Provider (AI 提供商) 管理 ============

@app.get("/providers")
async def list_providers():
    providers = {
        name: {
            "model": p.model,
            "api_base": p.api_base,
        }
        for name, p in provider_registry.providers.items()
    }
    return {"active": provider_registry.active, "providers": providers}


@app.post("/providers")
async def add_provider(request: ProviderAddRequest):
    try:
        provider_registry.add(
            name=request.name,
            model=request.model,
            api_key=request.api_key,
            api_base=request.api_base,
        )
        return {"status": "ok", "message": f"Provider '{request.name}' added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/providers/{name}/activate")
async def activate_provider(name: str):
    try:
        provider_registry.set_active(name)
        return {"status": "ok", "message": f"Provider '{name}' activated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ MCP 管理 ============

class AddMcpServerRequest(BaseModel):
    """统一添加 MCP：本地 npm/command 或远程 URL。"""
    server_id: str
    # 远程
    url: str = ""
    transport: str = "sse"
    headers: dict = {}
    # 本地 npm
    package_name: str = ""
    args: list[str] = []
    # 本地 command
    command: str = ""


@app.post("/mcp/install/npm")
async def install_npm_mcp(req: InstallNpmRequest):
    try:
        result = mcp_installer.install_npm_server(req.package_name, req.server_id, req.args)
        # 安装成功后自动启动服务器
        if result.get("status") == "ok":
            server_config = mcp_config.get_server(req.server_id)
            if server_config:
                mcp_manager.add_from_config(req.server_id, server_config)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/mcp/servers")
async def add_mcp_server(req: AddMcpServerRequest):
    """添加 MCP server（远程 URL 或本地 npm/command）。"""
    server_id = (req.server_id or "").strip()
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id 不能为空")

    url = (req.url or "").strip()
    package_name = (req.package_name or "").strip()
    command = (req.command or "").strip()

    try:
        if url:
            config = {
                "url": url,
                "transport": (req.transport or "sse").strip() or "sse",
            }
            if req.headers:
                config["headers"] = req.headers
            mcp_config.add_server(server_id, config)
            ok = mcp_manager.add_from_config(server_id, config)
            if not ok:
                err = getattr(mcp_manager.servers.get(server_id), "last_error", None)
                # 即使连接失败也保留配置，方便用户鉴权后重连
                return {
                    "status": "saved",
                    "server_id": server_id,
                    "type": "remote",
                    "connected": False,
                    "message": err or "配置已保存，但当前连接失败（可能需要浏览器登录鉴权后重连）",
                    "config": config,
                }
            return {
                "status": "ok",
                "server_id": server_id,
                "type": "remote",
                "connected": True,
                "message": f"远程 MCP '{server_id}' 已连接",
                "config": config,
            }

        if package_name:
            result = mcp_installer.install_npm_server(package_name, server_id, req.args or [])
            if result.get("status") != "ok":
                raise HTTPException(status_code=400, detail=result.get("message") or "安装失败")
            server_config = mcp_config.get_server(server_id) or {}
            ok = mcp_manager.add_from_config(server_id, server_config)
            return {
                "status": "ok" if ok else "saved",
                "server_id": server_id,
                "type": "npm",
                "connected": bool(ok),
                "message": f"MCP '{server_id}' 已添加" + ("" if ok else "（启动失败，请检查日志）"),
                "config": server_config,
            }

        if command:
            config = {"command": command, "args": req.args or []}
            mcp_config.add_server(server_id, config)
            ok = mcp_manager.add_from_config(server_id, config)
            return {
                "status": "ok" if ok else "saved",
                "server_id": server_id,
                "type": "command",
                "connected": bool(ok),
                "message": f"MCP '{server_id}' 已添加" + ("" if ok else "（启动失败，请检查日志）"),
                "config": config,
            }

        raise HTTPException(status_code=400, detail="请提供 url、package_name 或 command 之一")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """删除 MCP server 配置并停止进程/连接。"""
    server_id = (server_id or "").strip()
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id 不能为空")
    mcp_manager.remove_server(server_id)
    mcp_config.remove_server(server_id)
    return {"status": "ok", "server_id": server_id, "message": f"MCP '{server_id}' 已删除"}


@app.post("/mcp/servers/{server_id}/reconnect")
async def reconnect_mcp_server(server_id: str):
    """按配置重连指定 MCP server。"""
    server_id = (server_id or "").strip()
    config = mcp_config.get_server(server_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"MCP '{server_id}' 不存在")
    mcp_manager.remove_server(server_id)
    ok = mcp_manager.add_from_config(server_id, config)
    client = mcp_manager.servers.get(server_id)
    err = getattr(client, "last_error", None) if client else "connect failed"
    return {
        "status": "ok" if ok else "error",
        "server_id": server_id,
        "connected": bool(ok),
        "message": "重连成功" if ok else (err or "重连失败"),
    }


@app.get("/mcp/config")
async def get_mcp_config():
    return mcp_config.data


@app.post("/mcp/config")
async def update_mcp_config(mcpServers: dict = None):
    """更新 MCP 配置（新格式）"""
    if mcpServers is not None:
        mcp_config.data["mcpServers"] = mcpServers
        mcp_config.save()
        # 重新启动服务器
        mcp_manager.stop_all()
        initialize_mcp_servers()
    return {"status": "ok", "config": mcp_config.data}


@app.get("/mcp/test")
async def test_mcp_connection():
    """测试 MCP 连接状态"""
    servers_status = {}
    # 已连接的
    for server_id, client in mcp_manager.servers.items():
        try:
            tools = client.list_tools()
            servers_status[server_id] = {
                "status": "connected",
                "tools_count": len(tools),
                "transport": getattr(client, "transport", "unknown"),
            }
        except Exception as e:
            servers_status[server_id] = {
                "status": "error",
                "error": str(e),
                "transport": getattr(client, "transport", "unknown"),
            }
    # 配置里有但未连接的
    for server_id, cfg in mcp_config.get_servers().items():
        if server_id not in servers_status:
            servers_status[server_id] = {
                "status": "disconnected",
                "config": cfg,
            }
    return {"servers": servers_status}


@app.get("/mcp/tools")
async def list_mcp_tools():
    """列出所有 MCP 工具（包括所有 server）"""
    try:
        mcp_tools = mcp_manager.list_tools_as_openai_format()
        return {"count": len(mcp_tools), "tools": mcp_tools}
    except Exception as e:
        return {"count": 0, "tools": [], "error": str(e)}


# ============ Native Tools 管理 ============

@app.get("/native/tools")
async def list_native_tools():
    """列出所有内置 native 工具（不含 skill 工具）"""
    tools = tool_registry.get_native_only_tools()
    return {"count": len(tools), "tools": tools}


@app.get("/skills/tools")
async def list_skill_tools():
    """列出所有 skill 注册的工具（skill__ 前缀）"""
    tools = tool_registry.get_skill_tools()
    return {"count": len(tools), "tools": tools}


@app.get("/mcp/tools/by_server")
async def list_mcp_tools_by_server():
    """按 server 分组列出 MCP 工具"""
    groups = []  # [{server_id, tools: [...], tool_count}]
    for server_id, client in mcp_manager.servers.items():
        try:
            raw_tools = client.list_tools()
            tools = []
            for t in raw_tools:
                schema = McpServerManager._sanitize_schema(t.get("inputSchema"))
                tools.append({
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": schema,
                    },
                })
            groups.append({
                "server_id": server_id,
                "tool_count": len(tools),
                "tools": tools,
            })
        except Exception as e:
            groups.append({
                "server_id": server_id,
                "tool_count": 0,
                "tools": [],
                "error": str(e),
            })
    return {"server_count": len(groups), "servers": groups}


# ============ Skill 管理 ============

class CreateSkillRequest(BaseModel):
    skill_name: str
    display_name: str = ""
    description: str = ""
    purpose: str = ""
    instructions: str = ""
    overwrite: bool = False


class InstallSkillGithubRequest(BaseModel):
    """对标: npx skills add <repo> --skill <name>"""
    repo_url: str
    skill_name: str = ""
    branch: str = ""
    overwrite: bool = False



@app.get("/skills")
async def get_skills():
    """获取所有已安装的 skill 列表"""
    skills = skill_registry.list()
    return {
        "skills": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
                "trigger_keywords": s.trigger_keywords,
            }
            for s in skills
        ]
    }


@app.post("/skills/install/github")
async def install_skill_github(req: InstallSkillGithubRequest):
    """从 GitHub 安装 skill（对标 npx skills add <repo> --skill <name>）"""
    from Symbix_sdk.skill.installer import install_skill_from_github

    if not (req.repo_url or "").strip():
        raise HTTPException(status_code=400, detail="repo_url 不能为空")
    result = install_skill_from_github(
        repo_url=req.repo_url,
        skill_name=req.skill_name,
        target_dir=skill_registry.skills_dir,
        branch=req.branch or "",
        overwrite=req.overwrite,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "安装 skill 失败")

    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "path": result.get("path"),
        "source": result.get("source"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@app.delete("/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """删除已安装 skill 并热刷新。"""
    from Symbix_sdk.skill.installer import uninstall_skill

    result = uninstall_skill(skill_name, skill_registry.skills_dir)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "删除失败")
    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@app.post("/skills/create")
async def create_skill(req: CreateSkillRequest):
    """创建 skill 骨架目录（调用 skill-creator/scripts/init_skill.py）"""

    try:
        # 延迟导入，避免启动时依赖路径问题
        from Symbix_sdk.skill.installed_skill.skill_creator_scripts import create_skill_skeleton  # type: ignore
    except Exception:
        # 直接从脚本路径加载
        import importlib.util
        init_path = os.path.join(
            BASE_DIR,
            "Symbix_sdk",
            "skill",
            "installed_skill",
            "skill-creator",
            "scripts",
            "init_skill.py",
        )
        if not os.path.exists(init_path):
            raise HTTPException(status_code=500, detail=f"init_skill.py 不存在: {init_path}")
        spec = importlib.util.spec_from_file_location("init_skill", init_path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        create_skill_skeleton = mod.create_skill_skeleton

    result = create_skill_skeleton(
        skill_name=req.skill_name,
        description=req.description,
        display_name=req.display_name,
        purpose=req.purpose,
        instructions=req.instructions,
        target_dir=skill_registry.skills_dir,
        overwrite=req.overwrite,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "创建 skill 失败")

    # 创建后立即重新扫描注册
    skill_registry.scan()
    tool_registry.refresh_skills()
    return {
        "status": "ok",
        "skill_name": result.get("skill_name"),
        "path": result.get("path"),
        "message": result.get("message"),
        "count": len(skill_registry.list()),
    }


@app.post("/skills/reload")
async def reload_skills():
    """重新扫描并加载 skills，并刷新已注册的 skill 工具"""
    skill_registry.scan()
    # 让 tool_registry 重新注册 skill 为可调用工具
    tool_registry.refresh_skills()
    return {"status": "ok", "count": len(skill_registry.list())}



@app.get("/skills/match")
async def match_skills(user_input: str):
    """根据用户输入匹配相关 skill"""
    matched = skill_registry.find_by_trigger(user_input)
    return {
        "matched": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "description": s.description,
            }
            for s in matched
        ]
    }

@app.get("/debug/skills-path")
def debug_skills_path():
    import os
    return {
        "skills_dir": skill_registry.skills_dir,
        "absolute_path": os.path.abspath(skill_registry.skills_dir),
        "cwd": os.getcwd(),
        "exists": os.path.exists(skill_registry.skills_dir),
        "loaded_skills": skill_registry.list_skills() if hasattr(skill_registry, 'list_skills') else list(skill_registry._skills.keys()),
    }
# ============ Markdown 导出 ============

SDK_CONFIG_DIR = os.path.join(BASE_DIR, "Symbix_sdk", "config", "history_list")
os.makedirs(SDK_CONFIG_DIR, exist_ok=True)

# sessions_index.json：id → title 元数据
SESSION_INDEX_PATH = os.path.join(SDK_CONFIG_DIR, "sessions_index.json")


def _load_index() -> dict:
    if not os.path.exists(SESSION_INDEX_PATH):
        return {}
    try:
        with open(SESSION_INDEX_PATH, "r", encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {}


def _save_index(data: dict):
    with open(SESSION_INDEX_PATH, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False, indent=2)


def _get_md_path(session_id: str) -> str:
    """按 session_id 返回 MD 文件路径"""
    return os.path.join(SDK_CONFIG_DIR, f"{session_id}.md")


def _get_index_title(session_id: str) -> str:
    """从 index 取标题，没有则返回原首条截取"""
    idx = _load_index()
    return idx.get(session_id, "未命名对话")


@app.post("/api/save_markdown")
async def save_markdown(payload: SessionPayload):
    """保存/覆盖当前会话为 Markdown 文件"""
    sid = payload.session_id or "default"
    md_content = f"# {payload.title}\n\n"
    for msg in payload.history:
        role_label = "**User**" if msg.role == "user" else "**Assistant**"
        md_content += f"### {role_label}:\n{msg.content}\n\n---\n\n"

    file_path = _get_md_path(sid)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    # 同步 index
    index = _load_index()
    index[sid] = payload.title or index.get(sid, "新对话")
    _save_index(index)

    return {"status": "success", "session_id": sid, "path": file_path}


@app.post("/api/delete_markdown")
async def delete_markdown(req: DeleteMarkdownRequest):
    """按 session_id 删除 Markdown + memory 中的消息/摘要"""
    sid = req.session_id or "default"
    file_path = _get_md_path(sid)
    if os.path.exists(file_path):
        os.remove(file_path)
    # 从 index 中移除
    index = _load_index()
    index.pop(sid, None)
    _save_index(index)
    # 清除该 session 的消息和摘要（不清除跨会话画像）
    try:
        memory.clear_session(sid)
    except Exception as e:
        print(f"[Memory] clear_session failed: {e}")
    return {"status": "success", "message": f"Deleted: {sid}.md"}


@app.post("/api/rename_session")
async def rename_session(req: RenameSessionRequest):
    """重命名会话标题（index + MD 文件标题行）"""
    sid = req.session_id
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="标题不能为空")

    index = _load_index()
    index[sid] = new_title
    _save_index(index)

    # 更新 MD 文件的第一行标题
    md_path = _get_md_path(sid)
    if os.path.exists(md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if lines and lines[0].startswith("# "):
            lines[0] = f"# {new_title}\n"
        with open(md_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return {"status": "success", "session_id": sid, "title": new_title}


@app.post("/api/generate_title")
async def generate_title(req: GenerateTitleRequest):
    """使用 AI 根据对话上下文生成简短标题（≤15 字）"""
    context = req.context
    if not context:
        return {"status": "skipped", "reason": "无对话上下文"}

    prompt = (
        "根据以下对话内容，生成一个简短的标题（不超过 15 个字）。"
        "直接返回标题，不要带引号、标点或多余说明：\n\n" + context
    )
    try:
        result = await symbix_client.chat(
            user_input=prompt,
            history=[],
            registry=skill_registry,
            tools=None,
        )
        title = result.get("content", "").strip().strip('"').strip("'")[:30]
        if len(title) > 15:
            title = title[:15] + "…"

        # 写入 index
        sid = req.session_id or "default"
        if sid and title:
            index = _load_index()
            index[sid] = title
            _save_index(index)

        return {"status": "success", "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ 启动入口 ============

if __name__ == "__main__":
    try:
        uvicorn.run(
            "main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            log_level="info",
        )
    finally:
        # 关闭时清理 MCP 服务器
        mcp_manager.stop_all()
        print("[MCP] All servers stopped")