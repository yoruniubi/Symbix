from fastapi import APIRouter, HTTPException
from application.schemas import InstallNpmRequest, AddMcpServerRequest, AddMcpServersRawRequest
from application.state import (
    mcp_config,
    mcp_installer,
    mcp_manager,
    mcp_oauth_store,
    start_oauth_connect,
    get_mcp_oauth_status,
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


@router.post("/mcp/install/uvx")
async def install_uvx_mcp(req: InstallNpmRequest):
    """安装 uvx 形式的 MCP server(py 生态,如 mcp-server-sqlite)。"""
    try:
        result = mcp_installer.install_uvx_server(
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
    api_key = (req.api_key or "").strip()

    try:
        if url:
            config = {
                "url": url,
                "transport": (req.transport or "sse").strip() or "sse",
            }
            if req.headers:
                config["headers"] = req.headers
            mcp_config.add_server(server_id, config)
            # API Key 单独存到顶层 mcp_api_key,不混入 server 配置。
            # 仅当用户显式填写才更新;留空则沿用旧 key(避免改其它字段误清)。
            if api_key:
                mcp_config.set_api_key(server_id, api_key)
            # 组装连接配置:headers 缺 Authorization 时用顶层 key 注入 Bearer
            connect_cfg = dict(config)
            key = mcp_config.get_api_key(server_id)
            if key:
                headers = dict(connect_cfg.get("headers") or {})
                headers.setdefault("Authorization", f"Bearer {key}")
                connect_cfg["headers"] = headers

            # 判断该 URL 是否可能走 OAuth:无 API Key 时尝试连接,
            # 若 401/鉴权失败则触发浏览器授权。
            ok = mcp_manager.add_from_config(server_id, connect_cfg)
            if not ok:
                # 失败的 client 不会进 mcp_manager.servers,失败原因在 manager.last_error
                err = mcp_manager.last_error or ""
                need_oauth = (not key) and any(
                    s in err.lower() for s in ("401", "unauthorized", "403", "authentication", "oauth")
                )
                if need_oauth:
                    # 已有 token 就直接用(OAuth 连接会自动带 token 重试)
                    # 启动后台 OAuth 连接任务:浏览器弹窗授权 -> 完成后自动连接
                    start_oauth_connect(server_id, url, connect_cfg)
                    return {
                        "status": "oauth_pending",
                        "server_id": server_id,
                        "type": "remote",
                        "connected": False,
                        "message": "需要 OAuth 登录授权,请在弹出的浏览器窗口中完成登录",
                        "config": config,
                    }
                return {
                    "status": "saved",
                    "server_id": server_id,
                    "type": "remote",
                    "connected": False,
                    "message": err or "配置已保存,但当前连接失败",
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


@router.post("/mcp/servers/raw")
async def add_mcp_servers_raw(req: AddMcpServersRawRequest):
    """直接接收一段 MCP 配置 JSON 片段,合并写入 mcp_config 并启动。

    适合任意本地 MCP(python -m xxx / node ./srv.js / 自定义 command)
    与远程 MCP(url),不需要 UI 为各模式开独立表单。
    上游需保证每个 server 配置至少包含启动所需字段(stdio: command+args;remote: url)。
    同名覆盖。支持 API Key 三种写法,见 AddMcpServersRawRequest 文档。
    """
    if not req.servers or not isinstance(req.servers, dict):
        raise HTTPException(status_code=400, detail="servers 不能为空且必须是 object")

    # 顶层 mcp_api_key 写法(1):先统一入库
    top_keys = req.mcp_api_key or {}
    if top_keys:
        for sid, key in top_keys.items():
            if key:
                mcp_config.set_api_key(str(sid), str(key))

    results = []
    for server_id, cfg in req.servers.items():
        server_id = (server_id or "").strip()
        if not server_id:
            results.append({"server_id": "(empty)", "status": "error", "message": "server_id 为空"})
            continue
        if not isinstance(cfg, dict):
            results.append({"server_id": server_id, "status": "error", "message": "配置必须是 object"})
            continue
        cfg_norm = {k: v for k, v in cfg.items() if v is not None}
        # 基本字段校验:远程需 url;本地需 command。
        if not cfg_norm.get("url") and not cfg_norm.get("command"):
            results.append({
                "server_id": server_id,
                "status": "error",
                "message": "配置必须含 url(远程)或 command(本地)",
            })
            continue
        try:
            # 写法(2):server 配置内嵌 api_key → 剥出存顶层,不污染 server 配置
            inline_key = (cfg_norm.pop("api_key", "") or "").strip()
            if inline_key:
                mcp_config.set_api_key(server_id, inline_key)
            elif server_id in top_keys:
                # 已由上方统一入库
                pass
            # 连接配置:headers 缺 Authorization 时注入顶层 key
            connect_cfg = dict(cfg_norm)
            key = mcp_config.get_api_key(server_id)
            if key:
                headers = dict(connect_cfg.get("headers") or {})
                headers.setdefault("Authorization", f"Bearer {key}")
                connect_cfg["headers"] = headers
            mcp_config.add_server(server_id, cfg_norm)
            ok = mcp_manager.add_from_config(server_id, connect_cfg)
            results.append({
                "server_id": server_id,
                "status": "ok" if ok else "saved",
                "connected": bool(ok),
                "message": ("已连接" if ok else "配置已保存但启动失败,请检查后端日志"),
            })
        except Exception as e:
            results.append({"server_id": server_id, "status": "error", "message": str(e)})

    all_ok = all(r.get("status") == "ok" for r in results)
    return {"status": "ok" if all_ok else "partial", "results": results}


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """删除 MCP server 配置并停止进程/连接。"""
    server_id = (server_id or "").strip()
    if not server_id:
        raise HTTPException(status_code=400, detail="server_id 不能为空")
    mcp_manager.remove_server(server_id)
    mcp_config.remove_server(server_id)
    # 级联清除 OAuth token(避免残留密钥)
    mcp_oauth_store.clear(server_id)
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
    cfg = dict(config)
    # 远程服务:注入顶层 mcp_api_key 的 Bearer
    if cfg.get("url"):
        key = mcp_config.get_api_key(server_id)
        if key:
            headers = dict(cfg.get("headers") or {})
            headers.setdefault("Authorization", f"Bearer {key}")
            cfg["headers"] = headers
    ok = mcp_manager.add_from_config(server_id, cfg)
    err = mcp_manager.last_error or ("connect failed" if not ok else None)
    if not ok and cfg.get("url"):
        # 无 API Key 且鉴权失败 -> 触发 OAuth 浏览器授权
        key = mcp_config.get_api_key(server_id)
        err_str = str(err or "")
        if (not key) and any(
            s in err_str.lower()
            for s in ("401", "unauthorized", "403", "authentication", "oauth")
        ):
            start_oauth_connect(server_id, cfg["url"], cfg)
            return {
                "status": "oauth_pending",
                "server_id": server_id,
                "connected": False,
                "message": "需要 OAuth 登录授权,请在弹出的浏览器窗口中完成登录",
            }
    return {
        "status": "ok" if ok else "error",
        "server_id": server_id,
        "connected": bool(ok),
        "message": "重连成功" if ok else (err or "重连失败"),
    }


@router.get("/mcp/oauth/status/{server_id}")
async def get_mcp_oauth_status_endpoint(server_id: str):
    """查询 MCP OAuth 连接任务状态(前端轮询)。"""
    server_id = (server_id or "").strip()
    st = get_mcp_oauth_status(server_id)
    # 补充 token 是否存在(前端显示"已授权"状态)
    tok = mcp_oauth_store.get_tokens_sync(server_id)
    st["has_token"] = bool(tok and tok.get("access_token"))
    st["connected"] = server_id in mcp_manager.servers
    return st


@router.delete("/mcp/oauth/token/{server_id}")
async def clear_mcp_oauth_token(server_id: str):
    """清除某 server 的 OAuth token(登出/重新授权)。"""
    server_id = (server_id or "").strip()
    mcp_oauth_store.clear(server_id)
    return {"status": "ok", "server_id": server_id, "message": "OAuth token 已清除"}


@router.post("/mcp/oauth/authorize/{server_id}")
async def authorize_mcp_oauth(server_id: str):
    """显式触发某 server 的 OAuth 浏览器授权(手动授权按钮)。

    适用场景:启动期静默降级失败、token 过期且 refresh 失效导致连不上时,
    用户点面板上的「授权」按钮主动弹浏览器完成登录。
    授权成功后后台会自动用新 token 重连 server。
    """
    server_id = (server_id or "").strip()
    config = mcp_config.get_server(server_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"MCP '{server_id}' 不存在")
    url = (config.get("url") or config.get("serverUrl") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail=f"MCP '{server_id}' 不是远程服务,无法 OAuth 授权")
    # 已有 token → 先清掉旧的(token 已失效时刷新会被拒,重授必须换新)
    # 仅清 tokens 保留 client_info(复用已有 client 注册,授权 URL 稳定)
    tok = mcp_oauth_store.get_tokens_sync(server_id)
    if tok:
        mcp_oauth_store.clear_tokens(server_id)
    start_oauth_connect(server_id, url, config)
    return {
        "status": "oauth_pending",
        "server_id": server_id,
        "connected": False,
        "has_old_token": bool(tok),
        "message": "已打开浏览器,请完成 OAuth 登录授权",
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
