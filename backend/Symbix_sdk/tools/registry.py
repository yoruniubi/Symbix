# tools/registry.py
from .native_tools import NativeToolkit

class ToolRegistry:
    """统一管理所有可调用工具，合并 native 和 mcp 两种来源"""

    def __init__(self, mcp_connector=None):
        self.native = NativeToolkit()
        self.native.setup_builtin_tools()
        self.mcp_connector = mcp_connector

    def get_openai_tools(self) -> list[dict]:
        tools = self.native.get_openai_tools()
        if self.mcp_connector:
            tools.extend(self.mcp_connector.list_tools_as_openai_format())
        return tools

    def execute(self, tool_name: str, arguments) -> str:
        if tool_name in self.native.tools:
            return self.native.execute_tool(tool_name, arguments)
        if self.mcp_connector:
            return self.mcp_connector.call_tool(tool_name, arguments)
        return f"[Error] Tool '{tool_name}' not found"