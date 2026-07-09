"""
Symbix Backend - FastAPI Server
提供 AI 对话、Skill 管理和 MCP 支持的 REST API
"""
import uvicorn
import asyncio
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
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

# 初始化 MCP servers（从配置文件启动）
def initialize_mcp_servers():
    """从配置文件启动所有 MCP servers"""
    servers = mcp_config.get_servers()
    for server_id, config in servers.items():
        command = config.get("command")
        args = config.get("args", [])
        if command:
            success = mcp_manager.add_server(server_id, command, args)
            if success:
                print(f"[MCP] Started server: {server_id}")
            else:
                print(f"[MCP] Failed to start server: {server_id}")

# 启动时初始化 MCP servers
initialize_mcp_servers()

# 使用 ToolRegistry 统一管理 native + mcp 工具
tool_registry = ToolRegistry(mcp_manager=mcp_manager)
# 把已加载的 skill 注册为可调用工具（出现在工具列表中）
tool_registry.set_skill_registry(skill_registry)


# ============ 请求模型 ============
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []
    system_prompt: str = ""
    api_key: str = ""
    api_base: str = ""
    model: str = ""
    use_mcp: bool = False


class ChatResponse(BaseModel):
    content: str
    session_id: str
    reasoning: str = None
    steps: list = []


# 需要用户确认的工具白名单（操作类工具）
APPROVAL_TOOLS = {"edit_file", "write_to_file", "replace_in_file", "delete_file", "run_command"}

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
    title: str
    history: List[MessageItem]


# ============ API 路由 ============

@app.get("/")
async def root():
    """根路径 - API 状态检查"""
    return {
        "status": "ok",
        "service": "Symbix API",
        "version": "0.1.0",
    }


@app.post("/chat")
async def chat(request: ChatRequest):
    try:
        # 直接用请求里的配置，不改 provider_registry
        api_key = request.api_key or provider_registry.get_active().api_key
        api_base = request.api_base or provider_registry.get_active().api_base
        model = request.model or provider_registry.get_active().model

        memory.add(request.session_id, "user", request.message)
        history = memory.get_history(request.session_id, limit=20)
        symbix_client.system_prompt = request.system_prompt

        # 决定是否传入 tools（native + mcp 统一由 ToolRegistry 管理）
        mcp_tools = None
        if request.use_mcp:
            mcp_tools = tool_registry.get_openai_tools()

        steps = []
        last_reasoning = None

        response = await symbix_client.chat(
            user_input=request.message,
            history=history[:-1],
            registry=skill_registry,
            tools=mcp_tools,
            override_api_key=api_key,
            override_api_base=api_base,
            override_model=model,
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
                        "user_input": request.message,
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
                user_input=request.message,
                history=history[:-1],
                registry=skill_registry,
                tools=mcp_tools,
                tool_results=tool_results,
                override_api_key=api_key,
                override_api_base=api_base,
                override_model=model,
            )
            last_reasoning = response.get("reasoning")

        memory.add(request.session_id, "assistant", response["content"])
        return ChatResponse(
            content=response["content"],
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


@app.post("/chat/approve")
async def chat_approve(req: ApproveRequest):
    ctx = _pending_approvals.pop(req.approval_id, None)
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

    memory.add(ctx["session_id"], "assistant", response["content"])
    return {
        "status": "ok",
        "content": response["content"],
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

            memory.add(request.session_id, "user", request.message)
            history = memory.get_history(request.session_id, limit=20)
            symbix_client.system_prompt = request.system_prompt

            mcp_tools = None
            if request.use_mcp:
                mcp_tools = tool_registry.get_openai_tools()

            steps = []
            full_text = ""

            # ── 第一轮流式 ──────────────────────────────────
            async for event in symbix_client.chat_stream(
                user_input=request.message,
                history=history[:-1],
                registry=skill_registry,
                tools=mcp_tools,
                override_api_key=api_key or None,
                override_api_base=api_base or None,
                override_model=model or None,
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
                            "user_input": request.message,
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

                # 构建带 tool 结果的消息序列回传
                msgs = symbix_client._build_messages(
                    history[:-1], request.message, registry=skill_registry, tools=mcp_tools
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
        return {"session_id": session_id, "messages": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
@app.post("/mcp/install/npm")
async def install_npm_mcp(req: InstallNpmRequest):
    try:
        result = mcp_installer.install_npm_server(req.package_name, req.server_id, req.args)
        # 安装成功后自动启动服务器
        if result.get("status") == "ok":
            server_config = mcp_config.get_server(req.server_id)
            if server_config:
                mcp_manager.add_server(req.server_id, server_config["command"], server_config["args"])
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
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
    for server_id, client in mcp_manager.servers.items():
        try:
            tools = client.list_tools()
            servers_status[server_id] = {
                "status": "connected",
                "tools_count": len(tools)
            }
        except Exception as e:
            servers_status[server_id] = {
                "status": "error",
                "error": str(e)
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
    """列出所有内置 native 工具"""
    tools = tool_registry.native.get_openai_tools()
    return {"count": len(tools), "tools": tools}


# ============ Skill 管理 ============

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

SDK_CONFIG_DIR = os.path.join(BASE_DIR, "Symbix_sdk", "config")
os.makedirs(SDK_CONFIG_DIR, exist_ok=True)


@app.post("/api/save_markdown")
async def save_markdown(payload: SessionPayload):
    """保存对话为 Markdown 文件"""
    md_content = f"# {payload.title}\n\n"
    for msg in payload.history:
        role_label = "**User**" if msg.role == "user" else "**Assistant**"
        md_content += f"### {role_label}:\n{msg.content}\n\n---\n\n"

    file_path = os.path.join(SDK_CONFIG_DIR, f"{payload.title}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    return {"status": "success", "path": file_path}


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