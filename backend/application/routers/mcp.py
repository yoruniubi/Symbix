"""MCP 管理路由。"""
from fastapi import APIRouter, HTTPException

from application.models import InstallNpmRequest, AddMcpServerRequest
from application.state import (
    mcp_config,
    mcp_installer,
    mcp_manager,
    initialize_mcp_servers,
)
from Symbix_sdk.mcp.connector import McpServerManager

router = APIRouter(tags=["mcp"])


@router.post("/mcp/install/npm")
async def install_npm_mcp(req: InstallNpmRequest):
    try:
        result = mcp_installer.install_npm_server(
            req.package_name, req.server_id, req.args
        )
        if result.get("status") == "ok":
            server_config = mcp_config.get_server(req.server_id)
            if server_config:
                mcp_manager.add_from_config(req.server_id, server_config)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/mcp/servers")
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
                return {
                    "status": "saved",
                    "server_id": server_id,
                    "type": "remote",
                    "connected": False,
                    "message": err
                    or "配置已保存，但当前连接失败（可能需要浏览器登录鉴权后重连）",
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
            result = mcp_installer.install_npm_server(
                package_name, server_id, req.args or []
            )
            if result.get("status") != "ok":
                raise HTTPException(
                    status_code=400, detail=result.get("message") or "安装失败"
                )
            server_config = mcp_config.get_server(server_id) or {}
            ok = mcp_manager.add_from_config(server_id, server_config)
            return {
                "status": "ok" if ok else "saved",
                "server_id": server_id,
                "type": "npm",
                "connected": bool(ok),
                "message": f"MCP '{server_id}' 已添加"
                + ("" if ok else "（启动失败，请检查日志）"),
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
                "message": f"MCP '{server_id}' 已添加"
                + ("" if ok else "（启动失败，请检查日志）"),
                "config": config,
            }

        raise HTTPException(
            status_code=400, detail="请提供 url、package_name 或 command 之一"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """删除 MCP server 配置并停止进程/连接。"""
    server_id = (server_id or "").strip()
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id 不能为空")
    mcp_manager.remove_server(server_id)
    mcp_config.remove_server(server_id)
    return {
        "status": "ok",
        "server_id": server_id,
        "message": f"MCP '{server_id}' 已删除",
    }


@router.post("/mcp/servers/{server_id}/reconnect")
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


@router.get("/mcp/config")
async def get_mcp_config():
    return mcp_config.data


@router.post("/mcp/config")
async def update_mcp_config(mcpServers: dict = None):
    """更新 MCP 配置（新格式）"""
    if mcpServers is not None:
        mcp_config.data["mcpServers"] = mcpServers
        mcp_config.save()
        mcp_manager.stop_all()
        initialize_mcp_servers()
    return {"status": "ok", "config": mcp_config.data}


@router.get("/mcp/test")
async def test_mcp_connection():
    """测试 MCP 连接状态"""
    servers_status = {}
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
    for server_id, cfg in mcp_config.get_servers().items():
        if server_id not in servers_status:
            servers_status[server_id] = {
                "status": "disconnected",
                "config": cfg,
            }
    return {"servers": servers_status}


@router.get("/mcp/tools")
async def list_mcp_tools():
    """列出所有 MCP 工具（包括所有 server）"""
    try:
        mcp_tools = mcp_manager.list_tools_as_openai_format()
        return {"count": len(mcp_tools), "tools": mcp_tools}
    except Exception as e:
        return {"count": 0, "tools": [], "error": str(e)}


@router.get("/mcp/tools/by_server")
async def list_mcp_tools_by_server():
    """按 server 分组列出 MCP 工具"""
    groups = []
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
