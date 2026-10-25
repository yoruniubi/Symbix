from __future__ import annotations
import json
import os
import time
import threading
from typing import Optional, TYPE_CHECKING
from Symbix_sdk.tools.risk_classifier import (
    classify_tool_risk,
    ToolRiskLevel
)

# 仅用于类型注解/IDE 静态分析,避免循环 import
if TYPE_CHECKING:
    from Symbix_sdk.config.mcp_config import McpConfig

# ---------- 工具元数据查找 ----------

def tool_meta(mcp_tools: Optional[list], tool_name: str) -> dict:
    """在含扩展字段的工具列表里查来源元数据。

    Returns: {"server_id": str, "annotations": dict}
    原生工具 / 查不到 → {"server_id": "builtin", "annotations": {}}
    """
    for t in mcp_tools or []:
        if not isinstance(t, dict) or t.get("type") != "function":
            continue
        fn = t.get("function") or {}
        if fn.get("name") == tool_name:
            return {
                "server_id": t.get("_mcp_server_id") or "builtin",
                "annotations": t.get("_mcp_annotations") or {},
            }
    return {"server_id": "builtin", "annotations": {}}


# ---------- MCP server 信任(持久化到 mcp_config)----------

_trust_store: Optional[McpConfig] = None


def _get_trust_store():
    """延迟绑定 application.state 的 mcp_config 单例,避免循环 import。"""
    global _trust_store
    if _trust_store is None:
        try:
            from application.state import mcp_config
            _trust_store = mcp_config
        except Exception:
            _trust_store = None
    return _trust_store


def is_server_trusted(server_id: str) -> bool:
    """server 是否被用户显式信任。仅 trusted 的 server 采信其 MCP annotations。"""
    store = _get_trust_store()
    if not store or not server_id or server_id == "builtin":
        return False
    try:
        cfg = store.get_server(server_id) or {}
        return bool(cfg.get("trusted"))
    except Exception:
        return False


def set_server_trusted(server_id: str, trusted: bool) -> bool:
    """标记/取消标记 MCP server 信任。返回是否成功。"""
    store = _get_trust_store()
    if not store or not server_id:
        return False
    try:
        cfg = store.get_server(server_id)
        if cfg is None:
            return False
        cfg = dict(cfg)
        cfg["trusted"] = bool(trusted)
        store.add_server(server_id, cfg)
        # trust 降级(trusted→unknown)时,清除该 server 名下会话 grants
        if not trusted:
            _clear_server_grants(server_id)
        return True
    except Exception:
        return False


# ---------- 会话信任状态(SessionTrust)----------

class SessionTrust:
    """单个会话的信任状态(持久化到 config/risk_trust.json)。

    - mode: "normal" | "auto"(auto-pilot;会话级开关,随会话持久化)
    - grants: {channel: {"server_id": str, "scope": str, "granted_at": float}}
      通道级会话授权:仅 write 通道,用户批准一次后**永久记住**(直到面板手动清除),
      重启进程后仍生效 —— 无 TTL,授权即信任。
      write 的 grant 限 scope="workspace"(防 prompt injection 借早期信任写任意路径)。
      exec/delete/network 不记 grant:normal 下每次问,auto-pilot 下全放行,grant 无意义。
    """

    _MODES = ("normal", "auto")

    def __init__(self, session_id: str = "default") -> None:
        self.session_id: str = session_id
        self.mode: str = "normal"
        self.grants: dict = {}
        self.lock = threading.Lock()

    def set_mode(self, mode: str) -> None:
        if mode in self._MODES:
            with self.lock:
                self.mode = mode
            _persist_session_trust()

    def grant(self, channel: str, server_id: str = "builtin",
              scope: str = "workspace", ttl: float = 0.0) -> None:
        """记录一次通道级会话授权(approve 同意时调用)**永久有效**。

        仅 write 通道可记 grant:exec 靠 auto 白名单、delete/network 每次问,
        均不参与会话 grant(避免无效 grant 被误读为已授权)。
        ttl 参数保留仅为向后兼容(调用方可能传入),永久模式忽略它。
        """
        if channel != "write":
            return
        with self.lock:
            self.grants[channel] = {
                "server_id": server_id,
                "scope": scope,
                "granted_at": time.time(),
            }
        _persist_session_trust()

    def check(self, channel: str, server_id: str = "builtin",
              scope: str = "workspace") -> bool:
        """查询某通道是否已有授权(永久有效,无过期)。

        - grant 只对授予它的 server_id 生效(builtin 对 builtin)。
        - 仅 write 通道会有 grant;其余通道永远返回 False(每次问)。
        """
        if channel != "write":
            return False
        with self.lock:
            g = self.grants.get(channel)
            if not g:
                return False
            if g.get("server_id") != server_id:
                return False
            # write grant 仅 workspace scope 放行(超 scope 需重新审批)
            if g.get("scope") == "workspace" and scope != "workspace":
                return False
            return True

    def clear(self) -> None:
        with self.lock:
            self.grants.clear()
        _persist_session_trust()

    def to_dict(self) -> dict:
        """面板展示用:grant 无到期时间(永久),expires_in 恒为 -1。"""
        with self.lock:
            return {
                "mode": self.mode,
                "grants": {
                    k: {"server_id": v["server_id"], "scope": v["scope"],
                        "expires_in": -1, "granted_at": v.get("granted_at", 0)}
                    for k, v in self.grants.items()
                },
            }


# ---------- 会话信任持久化(config/risk_trust.json)----------

# backend/application/services/risk_context.py → backend/Symbix_sdk/config/
_TRUST_CONFIG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Symbix_sdk", "config", "risk_trust.json",
))

_trust_persist_lock = threading.Lock()
_trust_loaded = False


def _load_persisted_trust() -> None:
    """启动/首次访问时从 risk_trust.json 恢复会话信任(幂等,只加载一次)。"""
    global _trust_loaded
    if _trust_loaded:
        return
    _trust_loaded = True
    try:
        if not os.path.exists(_TRUST_CONFIG_PATH):
            return
        with open(_TRUST_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        for sid, entry in (data.get("sessions") or {}).items():
            st = SessionTrust(str(sid))
            m = entry.get("mode")
            if m in st._MODES:
                st.mode = m
            for ch, g in (entry.get("grants") or {}).items():
                if isinstance(g, dict) and g.get("server_id"):
                    st.grants[ch] = {
                        "server_id": g["server_id"],
                        "scope": g.get("scope", "workspace"),
                        "granted_at": g.get("granted_at", 0),
                    }
            _session_trusts[sid] = st
    except Exception:
        pass


def _persist_session_trust() -> None:
    """把当前全部会话信任写盘(改 mode / grant / clear 时同步落盘)。"""
    payload = {"sessions": {}}
    with _session_trusts_lock:
        for sid, st in _session_trusts.items():
            payload["sessions"][sid] = {
                "mode": st.mode,
                "grants": {
                    k: {"server_id": v["server_id"], "scope": v["scope"],
                        "granted_at": v.get("granted_at", 0)}
                    for k, v in st.grants.items()
                },
            }
    try:
        os.makedirs(os.path.dirname(_TRUST_CONFIG_PATH), exist_ok=True)
        with _trust_persist_lock:
            with open(_TRUST_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# 会话信任注册表(进程内缓存 + 磁盘持久化)。key: session_id
_session_trusts: dict = {}
_session_trusts_lock = threading.Lock()


def get_session_trust(session_id: str) -> SessionTrust:
    """取(或创建)某会话的信任状态;首次访问时先从磁盘恢复。"""
    _load_persisted_trust()
    with _session_trusts_lock:
        st = _session_trusts.get(session_id)
        if st is None:
            st = SessionTrust(session_id)
            _session_trusts[session_id] = st
        return st


def _clear_server_grants(server_id: str) -> None:
    """server 从 trusted 降级时清除其名下所有会话 grants(并落盘)。"""
    changed = False
    with _session_trusts_lock:
        for st in _session_trusts.values():
            with st.lock:
                for ch in list(st.grants):
                    if st.grants[ch].get("server_id") == server_id:
                        st.grants.pop(ch, None)
                        changed = True
    if changed:
        _persist_session_trust()


def clear_session(session_id: str) -> None:
    """删除某会话全部信任状态(内存 + 磁盘)。"""
    _load_persisted_trust()
    with _session_trusts_lock:
        _session_trusts.pop(session_id, None)
    _persist_session_trust()


# ---------- exec 命令白名单(配置制)----------

# backend/application/services/risk_context.py → backend/Symbix_sdk/config/
_EXEC_WHITELIST_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "Symbix_sdk", "config", "exec_whitelist.json",
))

_exec_whitelist_cache: Optional[list] = None
_exec_whitelist_lock = threading.Lock()


def _load_exec_whitelist() -> list:
    """加载 exec 命令白名单配置(config/exec_whitelist.json)。

    结构:{ "commands": ["git status", "git diff", "ls"], "project_scope": null }
    命令匹配规则:参数以白名单命令开头即放行(前缀匹配);空配置则白名单为空(全拦)。
    """
    global _exec_whitelist_cache
    if _exec_whitelist_cache is not None:
        return _exec_whitelist_cache
    try:
        if os.path.exists(_EXEC_WHITELIST_PATH):
            with open(_EXEC_WHITELIST_PATH, "r", encoding="utf-8") as f:
                import json
                data = json.load(f) or {}
                cmds = [c.strip().lower() for c in (data.get("commands") or []) if c and c.strip()]
                _exec_whitelist_cache = cmds
                return cmds
    except Exception:
        pass
    _exec_whitelist_cache = []
    return _exec_whitelist_cache


def is_exec_whitelisted(command: str) -> bool:
    """命令是否在 exec 白名单内(前缀匹配)。用于 auto 模式放行安全命令。"""
    cmd = (command or "").strip().lower()
    if not cmd:
        return False
    return any(cmd.startswith(c) for c in _load_exec_whitelist())


def _default_exec_whitelist() -> list:
    """首次无配置时给出保守默认(用户可改)。"""
    return ["git status", "git diff", "git log", "git add", "ls", "dir", "pwd", "whoami"]


def ensure_exec_whitelist_exists() -> None:
    """若 config/exec_whitelist.json 不存在则生成默认文件。"""
    if os.path.exists(_EXEC_WHITELIST_PATH):
        return
    import json
    os.makedirs(os.path.dirname(_EXEC_WHITELIST_PATH), exist_ok=True)
    with open(_EXEC_WHITELIST_PATH, "w", encoding="utf-8") as f:
        json.dump({"commands": _default_exec_whitelist(), "project_scope": None},
                  f, ensure_ascii=False, indent=2)


# ---------- 统一分类入口 ----------

def classify_for_chat(tool_name: str, arguments, mcp_tools: Optional[list],
                      session_id: str, *, scope: str = "workspace") -> tuple:
    """统一风险分类(供 chat 各审批点调用)。

    决策链:
      1. 查工具元数据(server_id / annotations)→ risk_classifier 分类
      2. 会话级信任:read 直接放行;auto-pilot(会话开关)开启即**全通道放行**
         (含 exec / delete / network,用户显式授权本会话不再询问);
         normal 下已有通道 grant(永久记住)放行,其余首次审批

    Returns:
        (risk: ClassifyResult, needs_approval: bool, auto_passed: bool)
    """
    meta = tool_meta(mcp_tools, tool_name)
    server_id = meta["server_id"]
    annotations = meta["annotations"]
    trusted = is_server_trusted(server_id)

    risk = classify_tool_risk(
        tool_name,
        arguments,
        server_id=server_id,
        annotations=annotations,
        server_trust="trusted" if trusted else "unknown",
    )

    # SAFE(声明 read / override safe / annotation readOnly 等):直接放行
    if risk.level == ToolRiskLevel.SAFE:
        return risk, False, True

    st = get_session_trust(session_id)
    auto = st.mode == "auto"

    # auto-pilot:会话级显式授权,开启即全权放行(所有通道,含 exec/delete/network)。
    # 这是用户主动开的开关,语义就是「本轮会话别再问我」;有疑虑时关掉即可。
    if auto:
        return risk, False, True

    # ---- 以下为 normal 模式 ----
    # exec 通道:一律审批
    if risk.channel == "exec":
        return risk, True, False

    # write 等:已有该通道的会话 grant(永久)→ 放行
    if st.check(risk.channel, server_id=server_id, scope=scope):
        return risk, False, True

    # 其余(normal 下 delete/network/exec/write 首次)审批
    return risk, True, False


# ---------- 自然语言 trust 指令(轻量识别)----------

_TRUST_ON_PATTERNS = [
    r"(?<!关闭)(?<!退出)(?<!停用)(?<!关)auto[- ]?pilot",
    r"(开启|打开|启用)?(自动模式|自动干活)",
    r"别再(问我|问了|审批)", r"自动(批准|放行|执行)", r"autopilot",
    r"trust this session", r"trusted mode",
]
_TRUST_OFF_PATTERNS = [
    r"(关闭|退出|停用|关) ?(auto[- ]?pilot|autopilot|自动模式)",
    r"(回到|改回|恢复) ?(normal|逐次|逐次确认|确认模式)",
    r"normal mode", r"每次(都要)?(问我|问|确认|审批)", r"不用? auto" ,
]


def maybe_apply_trust_command(session_id: str, text: str) -> tuple[str, bool]:
    """识别用户消息中的 auto-pilot 开关指令并应用,返回 (处理后的文本, 是否消费)。

    - 开:auto-pilot(会话级,持久化)
    - 关:回到 normal
    指令命中时从消息里移除指令片段(避免污染发给模型的上下文),仅返回提示文本占位。
    """
    import re
    t = text or ""
    low = t.lower()
    if not session_id:
        return t, False
    st = get_session_trust(session_id)
    off = [p for p in _TRUST_OFF_PATTERNS if re.search(p, low)]
    on = [p for p in _TRUST_ON_PATTERNS if re.search(p, low)]
    if off:
        st.set_mode("normal")
        return "(已关闭 auto-pilot,恢复逐次确认。)", True
    if on:
        st.set_mode("auto")
        return "(已开启 auto-pilot:写入与白名单命令自动放行,高危操作仍会确认。)", True
    return t, False


# ---------- 状态查询(供面板 / 路由)----------

def list_sessions_trust() -> dict:
    """返回所有会话的 trust 状态(供面板展示;含磁盘恢复项)。"""
    _load_persisted_trust()
    out = {}
    with _session_trusts_lock:
        for sid, st in _session_trusts.items():
            out[sid] = st.to_dict()
    return out