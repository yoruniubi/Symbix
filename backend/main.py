"""
Symbix Backend - FastAPI Server
提供 AI 对话、Skill 管理和 MCP 支持的 REST API
"""
import uvicorn
from fastapi import FastAPI, HTTPException,WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from Symbix_sdk.client import SymbixClient
from Symbix_sdk.providers import ProviderRegistry
from Symbix_sdk.memory import ConversationMemory
from Symbix_sdk.config.mcp_config import McpCofing
from Symbix_sdk.mcp.connector import Connector
from Symbix_sdk.stt.sensevoice_cpp import SenseVoiceCppProvider

# ============ FastAPI App ============
app = FastAPI(title="Symbix API", version="0.1.0")

# ============ 初始化核心组件 ============
memory = ConversationMemory(db_path="memory.db")
provider_registry = ProviderRegistry(config_path="providers.json")

# 尝试初始化 provider registry，如果没有配置则使用默认值
try:
    _ = provider_registry.get_active()
except RuntimeError:
    provider_registry.add("default", "gpt-4o-mini")

symbix_client = SymbixClient(registry=provider_registry)

# ============ MCP 配置与连接 ============
mcp_config = McpCofing(path="mcp_config.json")

# 初始化sensevoice
stt = SenseVoiceCppProvider()

@app.websocket("/stt/stream")
async def stt_stream(websocket: WebSocket):
    await websocket.accept()

    async def on_result(text: str):
        await websocket.send_text(text)

    try:
        await stt.start_stream(on_result)
    except Exception as e:
        await websocket.send_text(f"[error] {e}")
    finally:
        stt.stop()
        await websocket.close()

def get_mcp_connector() -> Connector:
    """创建 MCP Connector 实例"""
    return Connector(
        host=mcp_config.data.get("host", "localhost"),
        port=mcp_config.data.get("port", 8000),
        username=mcp_config.data.get("username", "admin"),
        password=mcp_config.data.get("password", "admin"),
    )


# ============ 请求模型 ============
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []
    system_prompt: str = ""


class ChatResponse(BaseModel):
    content: str
    session_id: str


class ProviderAddRequest(BaseModel):
    name: str
    model: str
    api_key: str = None
    api_base: str = None


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
    """
    AI 对话接口
    接收用户消息，返回 AI 回复
    """
    try:
        # 保存用户消息到记忆
        memory.add(request.session_id, "user", request.message)

        # 获取历史消息
        history = memory.get_history(request.session_id, limit=20)

        # 更新 client 的 system prompt
        symbix_client.system_prompt = request.system_prompt

        # 调用 AI
        response = await symbix_client.chat(
            user_input=request.message,
            history=history[:-1],  # 排除刚添加的用户消息
        )

        # 保存 AI 回复到记忆
        memory.add(request.session_id, "assistant", response["content"])

        return ChatResponse(
            content=response["content"],
            session_id=request.session_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    AI 流式对话接口 (SSE)
    返回 Server-Sent Events 格式的流式响应
    """
    from fastapi.responses import StreamingResponse

    async def generate():
        try:
            memory.add(request.session_id, "user", request.message)
            history = memory.get_history(request.session_id, limit=20)
            symbix_client.system_prompt = request.system_prompt

            full_response = ""
            async for chunk in symbix_client.chat_stream(
                user_input=request.message,
                history=history[:-1],
            ):
                full_response += chunk
                yield f"data: {chunk}\n\n"

            memory.add(request.session_id, "assistant", full_response)
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.get("/history/{session_id}")
async def get_history(session_id: str, limit: int = 20):
    """获取指定会话的对话历史"""
    try:
        history = memory.get_history(session_id, limit=limit)
        return {"session_id": session_id, "messages": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ Provider (AI 提供商) 管理 ============

@app.get("/providers")
async def list_providers():
    """列出所有 AI 提供商"""
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
    """添加新的 AI 提供商"""
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
    """激活指定的 AI 提供商"""
    try:
        provider_registry.set_active(name)
        return {"status": "ok", "message": f"Provider '{name}' activated"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============ Skill 管理 ============

@app.get("/skills")
async def list_skills():
    """列出所有可用的 Skills"""
    # TODO: 从 skill loader 获取实际 skill 列表
    return {"skills": []}


@app.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    """获取指定 Skill 的详情"""
    # TODO: 从 skill loader 获取实际 skill
    return {
        "name": skill_name,
        "description": "Skill placeholder",
    }


# ============ MCP 管理 ============

@app.get("/mcp/config")
async def get_mcp_config():
    """获取 MCP 配置"""
    return mcp_config.data


@app.post("/mcp/config")
async def update_mcp_config(
    host: str = None,
    port: int = None,
    username: str = None,
    password: str = None,
):
    """更新 MCP 配置"""
    kwargs = {}
    if host is not None:
        kwargs["host"] = host
    if port is not None:
        kwargs["port"] = port
    if username is not None:
        kwargs["username"] = username
    if password is not None:
        kwargs["password"] = password

    mcp_config.update(**kwargs)
    return {"status": "ok", "config": mcp_config.data}


@app.get("/mcp/test")
async def test_mcp_connection():
    """测试 MCP 服务连接"""
    connector = get_mcp_connector()
    result = connector._request("GET", "")
    if result is not None:
        return {"status": "connected", "data": result}
    else:
        raise HTTPException(status_code=503, detail="Cannot connect to MCP server")


@app.get("/mcp/resources/{resource_path:path}")
async def access_mcp_resource(resource_path: str):
    """访问 MCP 资源"""
    connector = get_mcp_connector()
    result = connector._request("GET", resource_path)
    if result is not None:
        return result
    else:
        raise HTTPException(status_code=502, detail="Failed to access MCP resource")


@app.post("/mcp/tools/{tool_name}")
async def call_mcp_tool(tool_name: str, arguments: dict = None):
    """调用 MCP 工具"""
    connector = get_mcp_connector()
    result = connector._request(
        "POST",
        f"tools/{tool_name}",
        json=arguments or {},
    )
    if result is not None:
        return result
    else:
        raise HTTPException(status_code=502, detail="Failed to call MCP tool")


# ============ 启动入口 ============

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info",
    )