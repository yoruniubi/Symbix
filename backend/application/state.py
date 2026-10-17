import os
import threading
from Symbix_sdk.client import SymbixClient
from Symbix_sdk.providers import ProviderRegistry
from Symbix_sdk.memory import ConversationMemory
from Symbix_sdk.memory.memory_store import MemoryStore
from Symbix_sdk.config.mcp_config import McpConfig
from Symbix_sdk.mcp.connector import McpServerManager
from Symbix_sdk.mcp.oauth import TokenStore, ensure_oauth_token
from Symbix_sdk.tools.registry import ToolRegistry
from Symbix_sdk.skill.registry import SkillRegistry
from Symbix_sdk.checkpoint import init_recorder as _init_checkpoint_recorder
from Symbix_sdk.job_schedule import JobManager
from Symbix_sdk.mcp.installer import McpInstaller
from Symbix_sdk.act_mode import ActModeController

# ============ 路径 ============
# backend/ 目录（application 的上一级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK_CONFIG_DIR = os.path.join(BASE_DIR, "Symbix_sdk", "config", "history_list")
os.makedirs(SDK_CONFIG_DIR, exist_ok=True)
SESSION_INDEX_PATH = os.path.join(SDK_CONFIG_DIR, "sessions_index.json")

# ============ 核心组件 ============
provider_registry = ProviderRegistry(
    config_path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "providers.json")
)
symbix_client = SymbixClient(registry=provider_registry)
act_mode_controller = ActModeController(symbix_client)
memory = ConversationMemory(
    db_path=os.path.join(BASE_DIR, "Symbix_sdk", "memory", "memory.db")
)

memory_store = MemoryStore(
    db_path=os.path.join(BASE_DIR, "Symbix_sdk", "memory", "memory.db"),
    llm_client=symbix_client,    # 指向下方已初始化的 symbix_client
)

# Checkpoint recorder：同 memory.db 同库，跨表 join 方便。
# 记录 Agent 对外部世界的副作用 (工具/文件/命令/MCP)，与对话文本 (memory) 正交。
checkpoint_recorder = _init_checkpoint_recorder(
    db_path=os.path.join(BASE_DIR, "Symbix_sdk", "memory", "memory.db"),
)

# Job schedule:同 memory.db 同级目录,独立 jobs.db + apscheduler 内置表。
# build() 会在 main.py lifespan startup 时注入业务依赖。
job_manager = JobManager(
    db_path=os.path.join(BASE_DIR, "Symbix_sdk", "memory", "jobs.db"),
)

skill_registry = SkillRegistry(
    skills_dir=os.path.join(BASE_DIR, "Symbix_sdk", "skill", "installed_skills")
)

try:
    _ = provider_registry.get_active()
except RuntimeError:
    provider_registry.add("default", "gpt-4o-mini")


# ============ MCP ============
mcp_config = McpConfig(
    path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "mcp_config.json")
)
mcp_installer = McpInstaller(
    config_path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "mcp_config.json")
)
mcp_manager = McpServerManager()
# OAuth token 持久化(含 access/refresh token,不入 git)
mcp_oauth_store = TokenStore(
    path=os.path.join(BASE_DIR, "Symbix_sdk", "config", "mcp_oauth.json")
)
# OAuth 连接任务状态(server_id -> 状态 dict)
_mcp_oauth_tasks: dict = {}

def _set_oauth_status(server_id: str, status: str, message: str = ""):
    _mcp_oauth_tasks[server_id] = {
        "server_id": server_id,
        "status": status,
        "message": message,
    }

def get_mcp_oauth_status(server_id: str) -> dict:
    """获取某 server 的 OAuth 连接任务状态。"""
    st = _mcp_oauth_tasks.get(server_id)
    if st:
        return dict(st)
    # 回退:看连接状态
    if server_id in mcp_manager.servers:
        return {"server_id": server_id, "status": "connected"}
    return {"server_id": server_id, "status": "idle"}

def start_oauth_connect(
    server_id: str,
    url: str,
    config: dict,
    timeout_seconds: int = 150,
):
    """在后台线程执行带 OAuth 的远程连接(含浏览器授权,可能耗时)。

    调用方同步拿到 "oauth_pending" 后,前端轮询 get_mcp_oauth_status。
    """
    import threading
    import time

    def _run():
        _set_oauth_status(server_id, "connecting", "正在连接远程服务...")
        try:
            # 组装带 OAuth 能力的连接配置
            cfg = dict(config)
            headers = dict(cfg.get("headers") or {})
            # 已有 API Key 时不走 OAuth(API Key 优先)
            api_key = mcp_config.get_api_key(server_id)
            if api_key and not headers.get("Authorization"):
                headers["Authorization"] = f"Bearer {api_key}"
                cfg["headers"] = headers
                # 有 key 直接同步连
                ok = mcp_manager.add_from_config(server_id, cfg)
                _set_oauth_status(server_id, "ok" if ok else "error",
                                  "连接成功" if ok else ("连接失败:" + str(mcp_manager.last_error or "") or ""))
                return
            cfg["headers"] = headers
            cfg["oauth"] = True
            cfg["oauth_store"] = mcp_oauth_store

            def cb(status: str):
                _set_oauth_status(server_id, status)

            cfg["oauth_status_cb"] = cb
            _set_oauth_status(server_id, "authorizing", "请在浏览器中完成登录授权...")
            ok = mcp_manager.add_from_config(server_id, cfg)
            if ok:
                _set_oauth_status(server_id, "ok", "连接成功")
            else:
                err = mcp_manager.last_error or "连接失败"
                _set_oauth_status(server_id, "error", str(err))
        except Exception as e:
            _set_oauth_status(server_id, "error", str(e))

    threading.Thread(target=_run, daemon=True, name=f"mcp-oauth-{server_id}").start()
    return {"server_id": server_id, "status": "oauth_pending"}



def initialize_mcp_servers():
    """从配置文件启动所有 MCP servers"""
    import time as _time

    servers = mcp_config.get_servers()
    # 快照迭代:get_servers() 返回的是活引用,MCP 面板可能在初始化期间增删
    for server_id, config in list(servers.items()):
        try:
            cfg = dict(config or {})
            # 远程服务:若顶层 mcp_api_key 有该 server 的 key,注入 Authorization: Bearer
            if cfg.get("url"):
                key = mcp_config.get_api_key(server_id)
                has_key = bool(key)
                if has_key:
                    headers = dict(cfg.get("headers") or {})
                    headers.setdefault("Authorization", f"Bearer {key}")
                    cfg["headers"] = headers
                # 无 API Key 但存过 OAuth token 且仍可刷新 → 启用 OAuth 自动续期
                # (token 过期但带 refresh_token,connector 遇 401 会静默刷新重连,
                #  不弹浏览器;否则启动后永远连不上,需手动重授)
                if not has_key:
                    tok = mcp_oauth_store.get_tokens_sync(server_id)
                    refreshable = bool(
                        tok
                        and (
                            tok.get("refresh_token")
                            or not tok.get("expires_at")
                            or float(tok.get("expires_at", 0)) > _time.time() + 30
                        )
                    )
                    if refreshable:
                        cfg["oauth"] = True
                        cfg["oauth_store"] = mcp_oauth_store
                        # 启动期不弹浏览器:refresh 失败就让用户在面板手动授权
                        cfg["oauth_no_browser_on_start"] = True
            success = mcp_manager.add_from_config(server_id, cfg)
            if success:
                print(f"[MCP] Started server: {server_id}")
            else:
                print(f"[MCP] Failed to start server: {server_id}")
        except Exception as e:
            print(f"[MCP] Failed to start server '{server_id}': {e}")


# 启动时初始化 MCP。
# 放后台线程:add_from_config 会 spawn 子进程并同步等 initialize 响应
# (最长 30 秒/个),若某个 stdio server 卡住,同步执行会让整个后端
# 连模块导入都完不成 —— 表现就是重启后一直起不来/卡死。
threading.Thread(
    target=initialize_mcp_servers,
    daemon=True,
    name="mcp-init",
).start()

# ============ 工具注册 ============
tool_registry = ToolRegistry(mcp_manager=mcp_manager)
tool_registry.set_skill_registry(skill_registry)
_pending_approvals: dict[str, dict] = {}
# 交互型工具(ask_clarifying_question)挂起的额外信息:id → {question, suggestions, context}
_pending_questions: dict[str, dict] = {}
# approval 请求会先从 pending 中取出上下文;在后续 LLM 请求尚未完成时,
# 重复点击/重复提交不能再看到 pending,否则会被误报为 404。记录处理中 ID,
# 让路由可以返回明确的“正在处理”状态,避免同一个写文件工具执行两次。
_processing_approvals: set[str] = set()

# ============ 进行中生成任务注册表 ============
_session_tasks: dict[str, set] = {}


def register_session_task(sid: str, task) -> None:
    """注册会话进行中的生成任务;生成器退出时主动注销。"""
    if not sid:
        return
    _session_tasks.setdefault(sid, set()).add(task)


def unregister_session_task(sid: str, task) -> None:
    """生成器结束/被取消时注销任务,避免泄漏引用。"""
    if not sid:
        return
    tasks = _session_tasks.get(sid)
    if tasks:
        tasks.discard(task)
        if not tasks:
            _session_tasks.pop(sid, None)


def cancel_session_tasks(sid: str) -> int:
    """取消该会话所有进行中的生成任务,返回取消个数。用于删除会话时终止 chat/action。"""
    tasks = _session_tasks.pop(sid, None)
    if not tasks:
        return 0
    cancelled = 0
    for t in list(tasks):
        if not t.done():
            t.cancel()
            cancelled += 1
    return cancelled

kill_session_activity = cancel_session_tasks  # 语义别名:删除会话时一键终止

# ============ 上下文压缩/记忆提取阈值 ============
# 压缩：消息多于 16 条时把旧消息摘要掉，只留最近 12 条
COMPRESS_THRESHOLD = 16
RECENT_KEEP = 12
# 记忆提取：门槛比压缩低（短对话也可能有值得记的事），
# 且按游标增量提取，只有新增消息够多才再跑一次，避免重复调用模型
EXTRACT_THRESHOLD = 6
EXTRACT_MIN_NEW = 2
