from __future__ import annotations
import asyncio
import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

def _json(payload: Dict[str, Any]) -> str:
    """统一返回：始终是 JSON 字符串，便于模型精确读取字段。"""
    return json.dumps(payload, ensure_ascii=False)

_SERVER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-]*$")

def _resolve_target_dir(registry: Any = None, default_dir: str = ".") -> str:
    """解析 skill 安装目录：优先用 SkillRegistry，否则用注入的默认目录。"""
    if registry is not None and getattr(registry, "skills_dir", None):
        return os.path.abspath(registry.skills_dir)
    return os.path.abspath(default_dir)

def _looks_like_repo_url(source: str) -> bool:
    """判断 source 是仓库地址（走 git clone）还是 CLI 目标（走 npx skills add）。"""
    s = (source or "").strip()
    if re.match(r"^(https?|git)://", s, re.I) or s.startswith("git@"):
        return True
    return "github.com/" in s.lower()


async def _reload_skills(registry: Any, on_changed: Any) -> tuple[bool, str]:
    """重新扫描 skill 目录并重注册 skill__* 工具，返回 (是否成功, 错误信息)。"""
    if registry is None:
        return False, "skill 注册表未注入"
    try:
        await asyncio.to_thread(registry.scan)
        if on_changed is not None:
            on_changed()
        return True, ""
    except Exception as exc:  # 扫描失败不该吞掉安装结果
        return False, str(exc)


async def install_skill(
    source: str,
    skill_name: str = "",
    branch: str = "",
    overwrite: bool = False,
    _skill_registry: Any = None,
    _skills_dir: str = ".",
    _on_skills_changed: Any = None,
) -> str:
    """从 GitHub 仓库或 skills CLI 安装 skill，并立即热加载到当前进程。

    :param source: 仓库地址（https://github.com/owner/repo）或 CLI 目标（owner/repo、包名）
    :param skill_name: 仓库内指定的 skill 名；留空则取仓库名兜底
    :param branch: git 分支（仅仓库地址模式生效）
    :param overwrite: 同名 skill 已存在时是否覆盖
    :return: JSON 字符串（status/method/skill_names/path/reloaded/message）
    """
    source = (source or "").strip()
    if not source:
        return _json({"status": "error", "message": "source 不能为空"})

    from Symbix_sdk.skill.skill_installer import (
        install_skill_from_github,
        install_skill_via_cli,
    )

    target_dir = _resolve_target_dir(_skill_registry, _skills_dir)
    method = "github" if _looks_like_repo_url(source) else "cli"
    try:
        if method == "github":
            # 注意形参顺序：(repo_url, skill_name, target_dir, branch, overwrite)
            result = await asyncio.to_thread(
                install_skill_from_github,
                source,
                skill_name,
                target_dir,
                branch,
                overwrite,
            )
        else:
            # 注意形参顺序：(package, target_dir, skill_name, overwrite)
            result = await asyncio.to_thread(
                install_skill_via_cli,
                source,
                target_dir,
                skill_name,
                overwrite,
            )
    except Exception as exc:  # 网络异常 / 缺 git / 缺 npx
        return _json({"status": "error", "method": method, "message": f"安装异常: {exc}"})

    if not result.get("ok"):
        return _json(
            {
                "status": "error",
                "method": method,
                "message": result.get("error") or "安装失败",
                "available": result.get("available") or [],
                "run_type": result.get("run_type") or "",
            }
        )

    names = [n for n in (result.get("skill_names") or [result.get("skill_name")]) if n]
    reloaded, reload_error = await _reload_skills(_skill_registry, _on_skills_changed)
    message = result.get("message") or ""
    if reloaded:
        message += "；已热加载，本轮之后可直接调用"
    return _json(
        {
            "status": "ok",
            "method": method,
            "skill_names": names,
            "path": result.get("path") or "",
            "reloaded": reloaded,
            "reload_error": reload_error,
            "message": message,
        }
    )


async def remove_skill(
    skill_name: str,
    _skill_registry: Any = None,
    _skills_dir: str = ".",
    _on_skills_changed: Any = None,
) -> str:
    """删除已安装的 skill 目录，并热加载刷新注册表。

    :param skill_name: 要删除的 skill 标识名
    :return: JSON 字符串
    """
    skill_name = (skill_name or "").strip()
    if not skill_name:
        return _json({"status": "error", "message": "skill_name 不能为空"})

    from Symbix_sdk.skill.skill_installer import uninstall_skill as _uninstall_skill_dir

    target_dir = _resolve_target_dir(_skill_registry, _skills_dir)
    try:
        result = await asyncio.to_thread(_uninstall_skill_dir, skill_name, target_dir)
    except Exception as exc:
        return _json({"status": "error", "message": f"卸载异常: {exc}"})

    if not result.get("ok"):
        return _json({"status": "error", "message": result.get("error") or "卸载失败"})

    reloaded, reload_error = await _reload_skills(_skill_registry, _on_skills_changed)
    return _json(
        {
            "status": "ok",
            "skill_name": skill_name,
            "reloaded": reloaded,
            "reload_error": reload_error,
            "message": result.get("message") or f"Skill '{skill_name}' 已删除",
        }
    )


def _resolve_pkg_runner(package_type: str) -> tuple[Optional[str], str]:
    """复用 McpInstaller 的运行器选择逻辑，返回 (command, mode)。

    `McpInstaller.__init__` 只保存路径，用空路径实例化仅做运行器探测，不会碰配置。
    """
    from Symbix_sdk.mcp.mcp_installer import McpInstaller

    probe = McpInstaller("")
    if (package_type or "").strip().lower() == "uvx":
        return probe._resolve_uvx_runner()
    return probe._resolve_pkg_runner()


def _build_pkg_config(package: str, package_type: str, extra_args: List[str]) -> Dict[str, Any]:
    """把包名翻译成 MCP server 配置；运行器缺失时返回 {"error": ...}。"""
    runner, mode = _resolve_pkg_runner(package_type)
    if not runner:
        if (package_type or "").strip().lower() == "uvx":
            return {"error": "未检测到 uvx / uv，且 SDK 内未捆绑 uv"}
        return {"error": "未检测到 Node.js(npx)，且 SDK 内未捆绑 bun"}

    if mode == "npx":
        args = ["-y", package] + extra_args
    elif mode == "bunx":
        args = ["x", package] + extra_args
    elif mode == "uv":
        args = ["tool", "run", package] + extra_args
    else:  # uvx
        args = [package] + extra_args
    return {"command": runner, "args": args}


async def _register_and_connect(
    mcp_config: Any,
    mcp_manager: Any,
    server_id: str,
    config: Dict[str, Any],
    api_key: str = "",
) -> Dict[str, Any]:
    """写入 MCP 配置并尝试连接（不抛异常，失败信息进返回值）。"""
    try:
        mcp_config.add_server(server_id, config)
        if api_key:
            mcp_config.set_api_key(server_id, api_key)
    except Exception as exc:
        return {
            "server_id": server_id,
            "status": "error",
            "connected": False,
            "message": f"写入 MCP 配置失败: {exc}",
        }

    # 把集中存放的 api_key 转成 Authorization 头再交给连接层
    connect_cfg = dict(config)
    if connect_cfg.get("url"):
        key = api_key or (mcp_config.get_api_key(server_id) or "")
        if key:
            headers = dict(connect_cfg.get("headers") or {})
            headers.setdefault("Authorization", f"Bearer {key}")
            connect_cfg["headers"] = headers

    error = ""
    try:
        connected = bool(await asyncio.to_thread(mcp_manager.add_from_config, server_id, connect_cfg))
    except Exception as exc:
        connected = False
        error = str(exc)
    else:
        if not connected:
            error = str(getattr(mcp_manager, "last_error", "") or "连接失败")

    tools_count: Optional[int] = None
    if connected:
        client = getattr(mcp_manager, "servers", {}).get(server_id)
        if client is not None:
            try:
                tools = await asyncio.to_thread(client.list_tools)
                tools_count = len(tools or [])
            except Exception:
                tools_count = None

    result: Dict[str, Any] = {
        "server_id": server_id,
        "status": "connected" if connected else "saved",
        "connected": connected,
        "config": config,
        "tools_count": tools_count,
    }
    if error:
        result["error"] = error
    if not connected and connect_cfg.get("url"):
        low = error.lower()
        if any(k in low for k in ("401", "403", "unauthorized", "oauth", "authorize")):
            result["hint"] = (
                "该远程服务需要授权：请让用户打开聊天界面右侧 MCP 面板点「连接 / 授权」完成 OAuth，"
                "或拿到 API Key 后用 api_key 参数重试。"
            )
    return result


async def _install_from_json(
    config_json: str,
    default_id: str,
    mcp_config: Any,
    mcp_manager: Any,
) -> str:
    """批量导入 MCP 配置：单个配置对象，或 {"mcpServers": {...}} 包装格式。"""
    try:
        data = json.loads(config_json)
    except json.JSONDecodeError as exc:
        return _json({"status": "error", "message": f"config_json 不是合法 JSON: {exc}"})
    if not isinstance(data, dict):
        return _json({"status": "error", "message": "config_json 必须是 JSON 对象"})

    if isinstance(data.get("mcpServers"), dict):
        servers = data["mcpServers"]
    else:
        if not default_id:
            return _json({"status": "error", "message": "单条配置模式下必须提供 server_id"})
        servers = {default_id: data}

    if not servers:
        return _json({"status": "error", "message": "config_json 里没有可安装的 server"})

    results = []
    for server_id, raw in servers.items():
        server_id = str(server_id).strip()
        if not _SERVER_ID_RE.match(server_id):
            results.append({"server_id": server_id, "status": "error", "message": "server_id 非法"})
            continue
        if not isinstance(raw, dict) or not (raw.get("url") or raw.get("command")):
            results.append(
                {
                    "server_id": server_id,
                    "status": "error",
                    "message": "配置缺少 url 或 command 字段",
                }
            )
            continue
        config = {k: v for k, v in raw.items() if v is not None}
        if not config.get("url") and not config.get("args"):
            config["args"] = []
        results.append(await _register_and_connect(mcp_config, mcp_manager, server_id, config))

    connected = [r["server_id"] for r in results if r.get("connected")]
    return _json(
        {
            "status": "ok" if connected else "saved",
            "installed": results,
            "connected": connected,
            "message": (
                f"已处理 {len(results)} 个 MCP server，其中 {len(connected)} 个连接成功。"
                "MCP 工具会在下一轮对话生效（需该会话开启 MCP）。"
            ),
        }
    )


async def install_mcp_server(
    server_id: str = "",
    config_json: str = "",
    url: str = "",
    package: str = "",
    package_type: str = "npm",
    command: str = "",
    args: Optional[List[str]] = None,
    transport: str = "sse",
    api_key: str = "",
    _mcp_binding: Optional[Dict[str, Any]] = None,
) -> str:
    """注册并连接一个 MCP server（npm 包 / uvx 包 / 本地命令 / 远程 URL / 整段配置）。

    四种安装模式任选其一（config_json 优先）：
      - config_json：完整配置 JSON（单个对象或 {"mcpServers": {...}}）
      - url：远程 MCP 端点（SSE / Streamable HTTP）
      - package + package_type：npm 包（如 @playwright/mcp）或 uvx 包
      - command + args：本地可执行文件

    注意：本工具**没有幂等保护以外的重建语义** —— 已存在同名 server 时
    连接层会先 kill 旧进程再拉起新进程。所以调用前先确认当轮上下文里的
    「你已经装好的扩展」里没有它；用终端跑 uv/pip/npm 装 MCP 相关包同理，
    会替换正在运行的依赖并把连接打断。

    :return: JSON 字符串（status/connected/tools_count/error）
    """
    binding = _mcp_binding or {}
    mcp_config = binding.get("config")
    mcp_manager = binding.get("manager")
    if mcp_config is None or mcp_manager is None:
        return _json(
            {"status": "error", "message": "MCP 扩展绑定未注入（应用未完成初始化），无法安装"}
        )

    server_id = (server_id or "").strip()
    extra_args = [str(a) for a in (args or [])]

    # 1) 整段配置导入（可一次装多个）
    if (config_json or "").strip():
        return await _install_from_json(config_json, server_id, mcp_config, mcp_manager)

    # 2) 单一安装模式
    config: Dict[str, Any]
    if (url or "").strip():
        config = {"url": url.strip(), "transport": (transport or "sse").strip()}
        if not server_id:
            host = urlparse(config["url"]).netloc or "remote"
            server_id = re.sub(r"[^A-Za-z0-9]+", "-", host).strip("-") or "remote"
    elif (package or "").strip():
        config = _build_pkg_config(package.strip(), package_type, extra_args)
        if config.get("error"):
            return _json({"status": "error", "message": config["error"]})
    elif (command or "").strip():
        config = {"command": command.strip(), "args": extra_args}
    else:
        return _json(
            {
                "status": "error",
                "message": "请提供 config_json / url / package / command 之一",
            }
        )

    if not _SERVER_ID_RE.match(server_id):
        return _json(
            {
                "status": "error",
                "message": f"server_id 非法: {server_id!r}（仅允许字母、数字、下划线与连字符）",
            }
        )

    result = await _register_and_connect(
        mcp_config, mcp_manager, server_id, config, api_key=api_key
    )
    result["message"] = (
        f"MCP server '{server_id}' 已注册"
        + ("并连接成功。" if result.get("connected") else "，但连接失败。")
        + "MCP 工具会在下一轮对话生效（需该会话开启 MCP）。"
    )
    return _json(result)


async def remove_mcp_server(
    server_id: str,
    _mcp_binding: Optional[Dict[str, Any]] = None,
) -> str:
    """断开并删除一个 MCP server（含配置项与已存 API Key / OAuth 凭据）。

    :param server_id: 要删除的 server 标识
    :return: JSON 字符串
    """
    binding = _mcp_binding or {}
    mcp_config = binding.get("config")
    mcp_manager = binding.get("manager")
    oauth_store = binding.get("oauth_store")
    if mcp_config is None or mcp_manager is None:
        return _json(
            {"status": "error", "message": "MCP 扩展绑定未注入（应用未完成初始化），无法删除"}
        )

    server_id = (server_id or "").strip()
    if not server_id:
        return _json({"status": "error", "message": "server_id 不能为空"})

    existed = server_id in (mcp_config.get_servers() or {})

    # 先断开（会杀进程树，放线程里）
    try:
        await asyncio.to_thread(mcp_manager.remove_server, server_id)
    except Exception as exc:
        return _json({"status": "error", "message": f"断开连接失败: {exc}"})

    try:
        mcp_config.remove_server(server_id)
    except Exception as exc:  # Windows 文件锁等
        return _json(
            {"status": "error", "message": f"删除配置失败（连接已断开）: {exc}"}
        )

    if oauth_store is not None:
        try:
            oauth_store.clear(server_id)
        except Exception:
            pass

    return _json(
        {
            "status": "ok",
            "server_id": server_id,
            "removed": existed,
            "message": f"MCP server '{server_id}' 已删除" if existed else "该 server 本就不存在（已幂等处理）",
        }
    )


async def list_mcp_servers(_mcp_binding: Optional[Dict[str, Any]] = None) -> str:
    """列出已配置的 MCP server 及其连接状态。

    :return: JSON 字符串（servers: [{server_id, state, summary, error}]）
    """
    binding = _mcp_binding or {}
    mcp_config = binding.get("config")
    mcp_manager = binding.get("manager")
    if mcp_config is None:
        return _json({"status": "error", "message": "MCP 扩展绑定未注入"})

    servers = mcp_config.get_servers() or {}
    live = getattr(mcp_manager, "servers", {}) or {}
    starting = getattr(mcp_manager, "starting", set()) or set()
    failed = getattr(mcp_manager, "failed", {}) or {}

    items = []
    for server_id, cfg in servers.items():
        cfg = cfg if isinstance(cfg, dict) else {}
        if server_id in live:
            state = "connected"
        elif server_id in starting:
            state = "connecting"
        elif server_id in failed:
            state = "failed"
        else:
            state = "not_connected"
        if cfg.get("url"):
            summary = str(cfg["url"])
        else:
            summary = " ".join([str(cfg.get("command") or "")] + [str(a) for a in (cfg.get("args") or [])]).strip()
        item = {"server_id": server_id, "state": state, "summary": summary}
        if state == "failed":
            item["error"] = str(failed.get(server_id) or "")
        items.append(item)

    return _json({"status": "ok", "count": len(items), "servers": items})


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

EXTENSION_TOOLS_SCHEMAS = {
    "install_skill": {
        "risk_channel": "network",
        "func": install_skill,
        "description": (
            "从外部安装 Skill 到本地并立即热加载（可立刻使用）。"
            "支持两种来源：① GitHub 仓库地址（source 传 https://github.com/owner/repo，"
            "可选 skill_name 指定仓库内某个 skill、branch 指定分支）；"
            "② skills CLI 目标（source 传 owner/repo 短名或包名，如 'vercel-labs/agent-skills'）。"
            "当用户要求「装这个 skill」「从 GitHub 装 xx」或你搜到需要的 skill 仓库时调用。"
            "不知道确切仓库时，先用 search_online 查 GitHub 上的 SKILL.md 仓库再安装。"
            "同名 skill 已存在时需显式 overwrite=true 才会覆盖。"
            "安装会执行外部代码，属高风险操作，普通模式下需用户批准。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "GitHub 仓库地址（https://github.com/owner/repo）或 skills CLI 目标（owner/repo、包名）",
                },
                "skill_name": {
                    "type": "string",
                    "description": "仓库内的 skill 名；留空则用仓库名兜底/安装仓库内全部默认 skill",
                },
                "branch": {
                    "type": "string",
                    "description": "git 分支（仅仓库地址模式生效，留空用默认分支）",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "同名 skill 已存在时是否覆盖删除后重装，默认 false",
                },
            },
            "required": ["source"],
        },
    },
    "remove_skill": {
        "risk_channel": "delete",
        "func": remove_skill,
        "description": (
            "删除本地已安装的 Skill 并热加载刷新。"
            "用户要求卸载/删除某个 skill，或安装失败需要清理残留目录时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "要删除的 skill 标识名（installed_skills 下的目录名）",
                },
            },
            "required": ["skill_name"],
        },
    },
    "install_mcp_server": {
        "risk_channel": "network",
        "func": install_mcp_server,
        "description": (
            "注册并连接一个 MCP server，让它提供的工具在后续对话中可用。"
            "四种模式任选其一：① config_json 传整段配置（单个对象或 {\"mcpServers\": {...}}，可一次装多个）；"
            "② url 传远程端点（配合 transport=sse 或 streamable-http，需要密钥时带 api_key）；"
            "③ package + package_type 传包名（npm 如 @playwright/mcp，或 uvx 的 python 包）；"
            "④ command + args 传本地可执行文件。"
            "当用户要求「装个 MCP」「接入 xx 的 MCP server」时调用。"
            "**装之前先看当轮上下文里的「你已经装好的扩展」；那不是空的就先别装** ——"
            "同一个 server 再装一次会顶掉正在跑的进程（先杀后起），"
            "而用终端跑 npx/uvx/pip 装包会替换它的依赖，连接直接断掉。"
            "确实要换成另一份配置时，先 remove_mcp_server 再装。"
            "会拉起外部进程 / 连接外部服务，属高风险操作，普通模式下需用户批准。"
            "装完的新工具下一轮对话才可见，且需要该会话开启 MCP。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "server 标识（字母数字下划线连字符，如 playwright、fetch）。config_json 使用 mcpServers 包装格式时可省略",
                },
                "config_json": {
                    "type": "string",
                    "description": "完整配置 JSON 字符串，支持单条配置对象或 {\"mcpServers\": {\"id\": {...}}} 批量格式",
                },
                "url": {
                    "type": "string",
                    "description": "远程 MCP 端点 URL（SSE / Streamable HTTP）",
                },
                "package": {
                    "type": "string",
                    "description": "包名：npm 包（如 @playwright/mcp）或 python 包（package_type=uvx）",
                },
                "package_type": {
                    "type": "string",
                    "enum": ["npm", "uvx"],
                    "description": "包类型，默认 npm",
                },
                "command": {
                    "type": "string",
                    "description": "本地 MCP server 可执行文件路径或命令名（stdio 模式）",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "传给 package / command 的额外参数",
                },
                "transport": {
                    "type": "string",
                    "description": "远程传输方式：sse（默认）或 streamable-http",
                },
                "api_key": {
                    "type": "string",
                    "description": "远程服务的 API Key（会存进配置并以 Bearer 头连接）",
                },
            },
        },
    },
    "remove_mcp_server": {
        "risk_channel": "delete",
        "func": remove_mcp_server,
        "description": (
            "断开并删除一个 MCP server（同时清掉配置项、已存 API Key 与 OAuth 凭据）。"
            "用户要求移除 MCP，或某 server 一直连接失败需要清理时调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "server_id": {
                    "type": "string",
                    "description": "要删除的 MCP server 标识",
                },
            },
            "required": ["server_id"],
        },
    },
    "list_mcp_servers": {
        "risk_channel": "read",
        "func": list_mcp_servers,
        "description": (
            "列出当前已配置的 MCP server 及连接状态（connected / connecting / failed / not_connected）。"
            "安装前确认是否已存在、排查连接失败原因时调用。只读，无副作用。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}
