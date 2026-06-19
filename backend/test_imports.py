"""Test imports for Symbix SDK"""
print("Testing imports...")

from Symbix_sdk import SymbixClient, ProviderRegistry, ConversationMemory, McpCofing, Connector
print("  Symbix_sdk top-level imports: OK")

from Symbix_sdk.client import SymbixClient
print("  client: OK")

from Symbix_sdk.providers import ProviderRegistry, ProviderConfig
print("  providers: OK")

from Symbix_sdk.memory import ConversationMemory
print("  memory: OK")

from Symbix_sdk.mcp import Connector, toolkit
print("  mcp: OK")

from Symbix_sdk.mcp.connector import Connector
print("  connector: OK")

from Symbix_sdk.mcp.native_tools import toolkit
print("  native_tools: OK")

from Symbix_sdk.skill.loader import SkillLoader
print("  skill.loader: OK")

from Symbix_sdk.config import McpCofing, AppConfig, ConfigManager
print("  config: OK")

print("\nAll imports successful!")