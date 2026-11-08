"""把「当前已经装好的扩展」压成一小段文本，放进当轮上下文。

Agent 并不知道自己装过什么：MCP 连上后它的工具确实在 tools 里，但**连接失败/
未连接/没开 MCP 的会话**里一个都看不到，于是模型会得出「还没装」的结论，
转身去 `install_mcp_server` 甚至直接在终端跑 `uv tool install`。
对 npx/uvx 来说重装 = 替换正在运行的 server 依赖，连接当场断掉。

所以这里把「注册了什么、连没连上、有几个工具」摊开给它看 ——
让它看见，而不是猜。
"""

from __future__ import annotations

from typing import Any, List, Optional

# MCP server 很多时别把上下文撑爆（真实用户一般 <10 个）
_MAX_ITEMS = 12


def _tool_count(mcp_manager: Any, server_id: str) -> Optional[int]:
    """取某个已连接 server 的工具数；拿不到就返回 None（不触发阻塞 RPC）。

    优先读 `_tools_cache`：连接时已经预热过，这里读缓存零成本；
    缓存为空时才走一次 list_tools()，失败也不影响主流程。
    """
    client = (getattr(mcp_manager, "servers", None) or {}).get(server_id)
    if client is None:
        return None
    cache = getattr(client, "_tools_cache", None)
    if cache is not None:
        return len(cache)
    try:
        return len(client.list_tools() or [])
    except Exception:
        return None


def _mcp_line(mcp_config: Any, mcp_manager: Any) -> str:
    """拼 MCP 那一行；没有注册任何 server 时返回空串。"""
    servers = (mcp_config.get_servers() if mcp_config is not None else None) or {}
    if not servers:
        return ""

    live = getattr(mcp_manager, "servers", None) or {}
    failed = getattr(mcp_manager, "failed", None) or {}

    parts: List[str] = []
    for server_id in list(servers.keys())[:_MAX_ITEMS]:
        # 状态后缀一律用方括号：server_id 是用户自己在面板起的名字，
        # 真实数据里就有 `alphaxiv(找论文)` 这种带圆括号的，圆括号套圆括号会读成一团。
        if server_id in live:
            count = _tool_count(mcp_manager, server_id)
            suffix = f" · {count} 个工具" if count is not None else ""
            parts.append(f"{server_id} [已连接{suffix}]")
        elif server_id in failed:
            parts.append(f"{server_id} [连接失败]")
        else:
            parts.append(f"{server_id} [未连接]")

    tail = "" if len(servers) <= _MAX_ITEMS else f" 等共 {len(servers)} 个"
    return "MCP：" + "、".join(parts) + tail


def _skill_line(skill_registry: Any) -> str:
    """只报 skill 数量；一个都没装时返回空串。

    完整清单（含 description / 触发关键词）已经由 `inject_skill_overview()`
    拼进 system 了，这里再抄一遍纯属浪费 token。这一行的作用是把
    「skill 和 MCP 一样，是已经装好的东西」这个心智点明，避免模型重复安装。
    """
    if skill_registry is None:
        return ""
    try:
        names = [getattr(s, "name", "") or "" for s in (skill_registry.list() or [])]
    except Exception:
        return ""
    total = len([n for n in names if n])
    if not total:
        return ""
    return f"Skill：已装 {total} 个（完整清单见系统提示的「可用技能列表」），同样不要重复安装"


def build_extension_status(
    mcp_config: Any = None,
    mcp_manager: Any = None,
    skill_registry: Any = None,
) -> str:
    """生成「当前扩展状态」段落，供 stream.py 拼进当轮上下文。

    Args:
        mcp_config: McpConfig，给出已注册的 server 列表
        mcp_manager: McpServerManager，给出连接状态与工具数
        skill_registry: SkillRegistry，给出已装 skill 名

    Returns:
        多行字符串（无末尾换行）；一个扩展都没有时返回空串，
        这样干净会话不会白带一段噪音。
    """
    lines = [ln for ln in (_mcp_line(mcp_config, mcp_manager), _skill_line(skill_registry)) if ln]
    if not lines:
        return ""

    header = "[你已经装好的扩展（实时状态，不要重复安装）]"
    rules = (
        "- 上面「已连接」的直接调用它的工具即可，**不要再装一遍**："
        "npx/uvx 重装会替换正在运行的 server 依赖，连接会当场断掉。\n"
        "- 想用上面没有的能力时，先说明缺什么、问过用户再装；"
        "不要自己用终端跑 uv / pip / npm 去装 MCP 相关的包。"
    )
    return "\n".join([header] + lines + [rules])
