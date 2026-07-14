# tools/registry.py
from .native_tools import NativeToolkit
from Symbix_sdk.mcp.connector import McpServerManager

class ToolRegistry:
    """统一管理所有可调用工具，合并 native 和 mcp 两种来源"""

    def __init__(self, mcp_manager: McpServerManager = None):
        self.native = NativeToolkit()
        self.native.setup_builtin_tools()
        self.mcp_manager = mcp_manager

    def set_skill_registry(self, registry):
        """关联 SkillRegistry，将每个已加载 skill 注册为可调用工具"""
        self.native.set_skill_registry(registry)

    def refresh_skills(self):
        """skill 重新加载后调用，刷新已注册的 skill 工具"""
        self.native.register_skill_tools()

    def get_openai_tools(self) -> list[dict]:
        tools = self.native.get_openai_tools()
        if self.mcp_manager:
            tools.extend(self.mcp_manager.list_tools_as_openai_format())
        return tools

    def get_native_only_tools(self) -> list[dict]:
        """返回仅原生内置工具（排除 skill 工具）"""
        return self.native.get_native_only_tools()

    def get_skill_tools(self) -> list[dict]:
        """返回仅 skill 工具"""
        return self.native.get_skill_tools()

    def execute(self, tool_name: str, arguments) -> str:
        # 优先在 native 工具中查找
        if tool_name in self.native.tools:
            return self.native.execute_tool(tool_name, arguments)
        
        # 在 MCP 工具中查找
        if self.mcp_manager:
            return self.mcp_manager.call_tool(tool_name, arguments)
        
        return f"[Error] Tool '{tool_name}' not found"