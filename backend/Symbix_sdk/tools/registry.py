import json as _json
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

    def is_async_tool(self, tool_name: str) -> bool:
        """该工具是否为异步工具(delegate_task 等),需走 execute_async。"""
        if tool_name in self.native.tools:
            return self.native.is_async_tool(tool_name)
        return False

    async def execute_async(
        self,
        tool_name: str,
        arguments,
        on_event=None,
        ctx: dict | None = None,
    ) -> str:
        """异步执行工具。原生异步工具走 await;其余回退到同步 execute。

        on_event / ctx 会注入给声明了同名形参的工具(delegate_task 用于进度推送与请求级模型参数)。
        """
        if isinstance(arguments, str):
            try:
                arguments = _json.loads(arguments) if arguments else {}
            except _json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments for tool '{tool_name}': {arguments!r}"
        if arguments is None:
            arguments = {}

        if tool_name in self.native.tools:
            return await self.native.execute_tool_async(
                tool_name, arguments, on_event=on_event, ctx=ctx
            )
        return self.execute(tool_name, arguments)

    def execute(self, tool_name: str, arguments) -> str:
        # 统一标准化 arguments：可能是 str(JSON) 或 dict，远端 MCP server 要 dict。
        # 模型有时把 arguments 当字符串传，则先解析。
        if isinstance(arguments, str):
            try:
                arguments = _json.loads(arguments) if arguments else {}
            except _json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments for tool '{tool_name}': {arguments!r}"
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return f"[Error] arguments must be an object/JSON string, got {type(arguments).__name__}"

        # 优先在 native 工具中查找
        if tool_name in self.native.tools:
            return self.native.execute_tool(tool_name, arguments)
        
        # 在 MCP 工具中查找
        if self.mcp_manager:
            return self.mcp_manager.call_tool(tool_name, arguments)
        
        return f"[Error] Tool '{tool_name}' not found"