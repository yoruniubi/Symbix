"""Test imports for Symbix SDK"""
print("Testing imports...")

from Symbix_sdk import SymbixClient, ProviderRegistry, ConversationMemory, McpConfig, Connector
print("  Symbix_sdk top-level imports: OK")

from Symbix_sdk import NativeToolkit, ToolRegistry, SkillRegistry, McpInstaller
print("  Symbix_sdk new exports: OK")

from Symbix_sdk.client import SymbixClient
print("  client: OK")

from Symbix_sdk.providers import ProviderRegistry, ProviderConfig
print("  providers: OK")

from Symbix_sdk.memory import ConversationMemory
print("  memory: OK")

from Symbix_sdk.mcp import Connector, McpInstaller
print("  mcp package: OK")

from Symbix_sdk.mcp.connector import Connector
print("  connector: OK")

from Symbix_sdk.mcp.installer import McpInstaller
print("  installer: OK")

from Symbix_sdk.tools.native_tools import NativeToolkit
print("  tools.native_tools: OK")

from Symbix_sdk.tools.registry import ToolRegistry
print("  tools.registry: OK")

from Symbix_sdk.skill.loader import SkillLoader
print("  skill.loader: OK")

from Symbix_sdk.skill.registry import SkillRegistry
print("  skill.registry: OK")

from Symbix_sdk.config.mcp_config import McpConfig
print("  config.mcp_config: OK")

# 实例化测试
try:
    tk = NativeToolkit()
    tk.setup_builtin_tools()
    tools = tk.get_openai_tools()
    print(f"  NativeToolkit instance: {len(tools)} builtin tools")
except Exception as e:
    print(f"  NativeToolkit instance: FAIL - {e}")

try:
    tr = ToolRegistry(mcp_manager=None)
    tools = tr.get_openai_tools()
    print(f"  ToolRegistry instance: {len(tools)} tools total")
except Exception as e:
    print(f"  ToolRegistry instance: FAIL - {e}")

try:
    sr = SkillRegistry(skills_dir="Symbix_sdk/skill/installed_skill")
    skills = sr.list()
    print(f"  SkillRegistry instance: {len(skills)} skills loaded")
except Exception as e:
    print(f"  SkillRegistry instance: FAIL - {e}")

print("\nAll imports successful!")