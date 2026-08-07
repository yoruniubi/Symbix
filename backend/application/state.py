"""
共享运行时状态：memory / registry / client / MCP 等单例。
路由模块通过 from application.state import xxx 引用，避免循环依赖。
"""
import os

from Symbix_sdk.client import SymbixClient
from Symbix_sdk.providers import ProviderRegistry
from Symbix_sdk.memory import ConversationMemory
from Symbix_sdk.memory.memory_store import MemoryStore
from Symbix_sdk.config.mcp_config import McpConfig
from Symbix_sdk.mcp.connector import McpServerManager
from Symbix_sdk.tools.registry import ToolRegistry
from Symbix_sdk.skill.registry import SkillRegistry
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
    extraction_model="gpt-4o-mini",
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


# 启动时初始化 MCP
initialize_mcp_servers()

# ============ 工具注册 ============
tool_registry = ToolRegistry(mcp_manager=mcp_manager)
tool_registry.set_skill_registry(skill_registry)

# ============ 审批白名单 & 待审批任务 ============
APPROVAL_TOOLS = {
    "edit_file",
    "write_to_file",
    "replace_in_file",
    "delete_file",
    "run_command",
    "open_terminal",
    "create_skill",
}
_pending_approvals: dict[str, dict] = {}

# ============ 上下文压缩阈值 ============
COMPRESS_THRESHOLD = 16
RECENT_KEEP = 12
