from __future__ import annotations
import os
import re
import json
from dataclasses import dataclass, field
from typing import Optional, Union

# ================= 常量 =================

class ToolRiskLevel:
    """风险等级常量"""
    SAFE = "safe"        # 只读操作,直接放行
    MEDIUM = "medium"    # 写入/修改操作,需审批
    HIGH = "high"        # 删除/执行命令,强制审批+警告


# 通道 → 基础风险等级
CHANNEL_LEVEL = {
    "read": ToolRiskLevel.SAFE,
    "write": ToolRiskLevel.MEDIUM,
    "exec": ToolRiskLevel.HIGH,
    "network": ToolRiskLevel.HIGH,
    "delete": ToolRiskLevel.HIGH,
}
CHANNEL_REASON = {
    "read": "只读/无副作用操作,安全放行",
    "write": "写入/修改操作,需确认",
    "exec": "执行命令/脚本,强制审批",
    "network": "网络/外部副作用,强制审批",
    "delete": "删除/破坏性操作,强制审批+警告",
}
# 多信号合并:取风险最高(优先级从高到低)
CHANNEL_PRIORITY = ["delete", "exec", "network", "write", "read"]

# 参数里可能出现的"高危关键字"(启发式上探用,防名字像 read 实为删除)
_DANGEROUS_CMD_PATTERNS = [
    r"rm\s+-rf", r"dd\s+if=", r"mkfs", r">\s*/dev/",
    r"format", r"del\s+/s", r"shutdown", r"reboot", r"chmod\s+777",
    r"curl\s+.*\|\s*(ba)?sh", r"wget\s+.*\|\s*(ba)?sh",
]
_CRITICAL_PATHS = ["/etc/", "/sys/", "/proc/", "C:\\Windows\\", "C:\\Program Files\\",
                   "/System", "/Library", "C:\\ProgramData"]
_CRITICAL_FILE_PATTERNS = [".env", "credentials", "secret", "id_rsa", "id_ed25519",
                           ".pgpass", "config.json"]


# ================= override 持久化(兼容旧裸名→builtin 复合 key)=================

_OVERRIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "risk_overrides.json",
)
_override_cache: Optional[dict] = None


def _load_overrides() -> dict:
    """加载 override 配置。旧版 key 为裸工具名,读取时迁移为 `builtin:<name>`。"""
    global _override_cache
    if _override_cache is not None:
        return _override_cache
    if not os.path.exists(_OVERRIDE_PATH):
        _override_cache = {}
        return _override_cache
    try:
        with open(_OVERRIDE_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
    except Exception:
        raw = {}
    migrated: dict = {}
    for k, v in raw.items():
        if ":" not in k:
            migrated[f"builtin:{k}"] = v  # 旧裸名 → builtin 前缀
        else:
            migrated[k] = v
    _override_cache = migrated
    return _override_cache


def _save_overrides(data: dict) -> None:
    global _override_cache
    _override_cache = data
    os.makedirs(os.path.dirname(_OVERRIDE_PATH), exist_ok=True)
    with open(_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_overrides() -> dict:
    """返回当前 override 配置(深拷贝,key 已含 server 前缀)。"""
    return json.loads(json.dumps(_load_overrides()))


def set_override(tool_key: str, level: str, reason: str = "") -> None:
    """新增/更新一条 override。tool_key 形如 `builtin:read_file` 或 `mcp__xx:tool`。"""
    if level not in (ToolRiskLevel.SAFE, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH):
        raise ValueError(f"invalid level: {level}")
    if ":" not in tool_key:
        tool_key = f"builtin:{tool_key}"  # 兼容调用方只传裸名
    data = _load_overrides()
    data[tool_key] = {"level": level, "reason": reason or f"自定义分级: {level}"}
    _save_overrides(data)


def remove_override(tool_key: str) -> bool:
    """删除一条 override。兼容裸名。"""
    data = _load_overrides()
    if ":" not in tool_key:
        tool_key = f"builtin:{tool_key}"
    if tool_key in data:
        del data[tool_key]
        _save_overrides(data)
        return True
    return False


# ================= 分类结果 =================

@dataclass(frozen=True)
class ClassifyResult:
    """一次工具调用的风险分类结果。

    相比旧二元组 (level, reason),多了 channel / confidence 供 UI 与审计;
    调用点取 res.level / res.reason 即可,加字段不破坏旧解包。
    """
    level: str                        # safe|medium|high
    reason: str
    channel: str = "write"            # read|write|exec|network|delete
    confidence: str = "fallback"      # declared(工具声明)|hint(MCP annotation)|guess(名字启发)|fallback(默认)
    server_id: str = "builtin"
    param_upgrade: bool = False       # 是否因参数命中危险模式而升级


# ================= 注册表查找 =================

def _all_native_schemas() -> dict:
    """返回 {tool_name: {"risk_channel": ...}}。延迟 import 避免循环。"""
    try:
        from Symbix_sdk.tools.tool_setup import ALL_TOOL_SCHEMAS
        return ALL_TOOL_SCHEMAS
    except Exception:
        return {}


def _native_channel(tool_name: str) -> Optional[str]:
    """从注册表查原生工具的 risk_channel。未找到返回 None。"""
    try:
        spec = _all_native_schemas().get(tool_name)
        if spec and spec.get("risk_channel"):
            return spec["risk_channel"]
    except Exception:
        pass
    return None


# ================= 通道/参数启发式 =================

def _merge_channels(channels: list) -> str:
    """多候选通道 → 取风险最高。channels 元素为 str 或 None。"""
    valid = [c for c in channels if c in CHANNEL_LEVEL]
    if not valid:
        return "write"
    return max(valid, key=lambda c: CHANNEL_PRIORITY.index(c))


def _heuristic_channel(tool_name: str) -> Optional[str]:
    """按工具名启发式猜通道(低置信度)。命中返回通道,否则 None。"""
    n = tool_name.lower()
    # 精确/前缀匹配,注意顺序:删除类词优先
    if any(k in n for k in ("delete", "remove", "purge", "clear", "destroy", "unlink", "truncate")):
        return "delete"
    if any(k in n for k in ("exec", "run", "command", "shell", "bash", "spawn", "terminal", "open_terminal")):
        return "exec"
    if any(k in n for k in ("fetch", "post", "put", "send", "http", "download", "upload", "request", "api",
                            "webhook", "notify", "email", "call_url", "invoke_remote", "mcp__")):
        return "network" if not any(k in n for k in ("get", "list", "search", "read", "query")) else "read"
    if any(k in n for k in ("get", "list", "search", "read", "query", "find", "show", "info", "status", "stat")):
        return "read"
    return None


def _param_danger(tool_name: str, arguments: dict) -> Optional[tuple]:
    """参数级危险检查:命中返回 (升级通道, reason),否则 None。

    只对命令/路径类参数做,防止误伤普通文本写入。
    """
    # 命令执行类:危险命令模式
    if tool_name in ("open_terminal",) or any(k in tool_name for k in ("exec", "command", "run", "shell")):
        cmd = str(arguments.get("command", "") or arguments.get("cmd", "") or "")
        for p in _DANGEROUS_CMD_PATTERNS:
            if re.search(p, cmd.lower()):
                return ("exec", f"危险命令: {cmd[:60]}")
    # 路径类:写入/删除系统关键路径
    path = str(arguments.get("file_path", "") or arguments.get("path", "") or arguments.get("target", ""))
    if path:
        low = path.lower()
        for cp in _CRITICAL_PATHS:
            if low.startswith(cp.lower()):
                return ("delete" if "delete" in tool_name or "remove" in tool_name else "exec",
                        f"操作系统关键路径: {path[:60]}")
        # 删除关键文件名
        if ("delete" in tool_name or "remove" in tool_name):
            for fp in _CRITICAL_FILE_PATTERNS:
                if fp in low:
                    return ("delete", f"删除关键文件: {path[:60]}")
    return None


# ================= 分类主入口 =================

def _classify_default(tool_name: str, arguments: dict, server_id: str = "builtin",
                      annotations: Optional[dict] = None, server_trust: str = "unknown") -> ClassifyResult:
    """核心分类:override 优先 → 声明通道 → MCP annotation → 启发式 → fallback。"""
    # 1) override(复合 key)最优先
    overrides = _load_overrides()
    key = f"{server_id}:{tool_name}" if server_id != "builtin" else f"builtin:{tool_name}"
    # 依次:精确复合 key → 裸名(旧版) → builtin: 前缀下的同名(UI 按裸名存的兜底)
    ov = (overrides.get(key)
          or overrides.get(tool_name)
          or (overrides.get(f"builtin:{tool_name}") if server_id != "builtin" else None))
    if ov:
        return ClassifyResult(
            level=ov.get("level", ToolRiskLevel.MEDIUM),
            reason=ov.get("reason", "自定义分级"),
            channel="write",  # override 不改变通道语义,仅改等级
            confidence="declared",
            server_id=server_id,
        )

    # 2) 参数级危险先查(最高优先,防"名字像 read 实为破坏")
    danger = _param_danger(tool_name, arguments)
    if danger:
        ch, reason = danger
        return ClassifyResult(
            level=CHANNEL_LEVEL.get(ch, ToolRiskLevel.HIGH),
            reason=reason,
            channel=ch,
            confidence="declared",
            server_id=server_id,
            param_upgrade=True,
        )

    # 3) 原生工具:声明通道
    if server_id == "builtin":
        ch = _native_channel(tool_name)
        if ch:
            return ClassifyResult(
                level=CHANNEL_LEVEL.get(ch, ToolRiskLevel.MEDIUM),
                reason=CHANNEL_REASON.get(ch, "原生工具"),
                channel=ch,
                confidence="declared",
                server_id="builtin",
            )

    # 4) MCP:annotation 归通道
    if server_id != "builtin":
        # 仅用户显式 trusted 的 server 才采信 annotations;未知 server 的 annotation 只是提示
        if server_trust == "trusted" and annotations:
            ann_ch = _mcp_annotation_channel(annotations)
            if ann_ch:
                return ClassifyResult(
                    level=CHANNEL_LEVEL.get(ann_ch, ToolRiskLevel.MEDIUM),
                    reason=f"MCP annotation 分类: {ann_ch}",
                    channel=ann_ch,
                    confidence="hint",
                    server_id=server_id,
                )
        # 未知 server:不采信名字启发(名字可伪造),保底 network —— 每次问,不给会话信任
        return ClassifyResult(
            level=CHANNEL_LEVEL["network"],
            reason=f"未知 MCP server({server_id})工具,保底按网络/外部副作用处理",
            channel="network",
            confidence="fallback",
            server_id=server_id,
        )

    # 5) 兜底
    ch = _heuristic_channel(tool_name)
    if ch:
        return ClassifyResult(
            level=CHANNEL_LEVEL.get(ch, ToolRiskLevel.MEDIUM),
            reason=f"按名字推测: {ch}",
            channel=ch,
            confidence="guess",
            server_id=server_id,
        )
    return ClassifyResult(
        level=ToolRiskLevel.MEDIUM,
        reason="未分类工具,需确认",
        channel="write",
        confidence="fallback",
        server_id=server_id,
    )


def _mcp_annotation_channel(annotations: dict) -> Optional[str]:
    """MCP annotations → 通道。仅受信任 server 调用。

    取所有 true hint 中风险最高的:
      destructiveHint → delete;readOnlyHint → read;openWorldHint → network;
      idempotentHint 不单列(不降级)。
    """
    if not isinstance(annotations, dict):
        return None
    candidates = []
    if annotations.get("readOnlyHint"):
        candidates.append("read")
    if annotations.get("destructiveHint"):
        candidates.append("delete")
    if annotations.get("openWorldHint"):
        candidates.append("network")
    if not candidates:
        return None
    return max(candidates, key=lambda c: CHANNEL_PRIORITY.index(c))


def classify_tool_risk(tool_name: str, arguments: Union[dict, str], *,
                       server_id: str = "builtin",
                       annotations: Optional[dict] = None,
                       server_trust: str = "trusted" if False else "unknown",
                       session_trust=None) -> ClassifyResult:
    """分析工具调用的风险等级(通道化)。

    Args:
        tool_name: 工具名(原生为裸名;MCP 由调用方拆出 server_id 后传裸名)
        arguments: 参数字典或 JSON 字符串
        server_id: 来源(原生 builtin;MCP 为 server id)
        annotations: MCP server 返回的 annotations(仅 trusted server 采信)
        server_trust: "trusted" | "unknown"(MCP server 信任级别)
        session_trust: 会话信任状态(第 4 步引入,预留)

    Returns:
        ClassifyResult(level, reason, channel, confidence, server_id, param_upgrade)
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}

    # 兼容:调用方直接传 "server_id:tool_name"(如 mcp__github:create_issue)
    if ":" in tool_name and server_id == "builtin":
        sid, _, tname = tool_name.partition(":")
        server_id, tool_name = sid, tname

    return _classify_default(tool_name, arguments, server_id=server_id,
                             annotations=annotations, server_trust=server_trust)


def get_effective_rules() -> dict:
    """返回合并后的生效规则(声明 + override),供前端展示。

    结构:{tool_key: {"level": str, "reason": str, "source": "declared"|"override"|"guess"}}
    原生工具 key 用裸名(builtin: 前缀剥离),MCP 复合 key 原样保留,兼容旧面板。
    """
    overrides = _load_overrides()
    result: dict = {}
    # 原生工具:从注册表枚举
    for name, spec in _all_native_schemas().items():
        ch = spec.get("risk_channel")
        if ch:
            result[name] = {
                "level": CHANNEL_LEVEL.get(ch, ToolRiskLevel.MEDIUM),
                "reason": CHANNEL_REASON.get(ch, spec.get("description", "")[:40]),
                "source": "declared",
                "channel": ch,
                "server_id": "builtin",
            }
    # override 覆盖
    for key, ov in overrides.items():
        display_key = key[7:] if key.startswith("builtin:") else key
        if display_key in result:
            result[display_key].update({
                "level": ov.get("level"),
                "reason": ov.get("reason", ""),
                "source": "override",
            })
        else:
            result[display_key] = {
                "level": ov.get("level", ToolRiskLevel.MEDIUM),
                "reason": ov.get("reason", ""),
                "source": "override",
                "channel": "write",
            }
    return result


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    test_cases = [
        ("read_file", {"file_path": "test.txt"}),
        ("list_files", {"directory": "."}),
        ("edit_file", {"file_path": "code.py", "content": "print('hello')"}),
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "./src.py"}),
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "C:\\Windows\\System32\\x.cfg"}),
        ("open_terminal", {"visible": True}),
        ("open_terminal", {"command": "rm -rf /", "visible": False}),
        ("open_terminal", {"command": "git status", "visible": False}),
        ("create_skill", {"name": "foo"}),
        ("search_online", {"query": "python"}),
        ("md_to_docx", {"md_content": "x", "out_path": "a.docx"}),
    ]
    print("风险分级测试(V2 通道化):")
    for tool_name, args in test_cases:
        r = classify_tool_risk(tool_name, args)
        print(f"  {tool_name:24s} -> {r.level.upper():6s} [{r.channel:7s}] ({r.confidence:8s}) {r.reason}")
