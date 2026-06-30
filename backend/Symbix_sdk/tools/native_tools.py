# tools/native_tools.py
"""
本地原生工具包
负责注册、管理和执行运行在本应用进程内部的 Python 函数工具
（例如：文件读写、桌宠状态控制等），与外部 MCP server 区分开
"""
from __future__ import annotations
from typing import Callable, Any
import json


class NativeToolkit:
    """本地原生工具包 - 注册、管理和执行本地 Python 函数工具"""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.tool_schemas: dict[str, dict] = {}

    def register_tool(
        self,
        name: str,
        func: Callable,
        description: str = "",
        parameters: dict | None = None,
    ):
        """注册工具函数，同时记录其 JSON Schema 描述

        Args:
            name: 工具名称
            func: 工具函数
            description: 工具功能描述（给 LLM 看）
            parameters: 参数 JSON Schema，例如
                {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "文件路径"},
                        "new_content": {"type": "string", "description": "新内容"}
                    },
                    "required": ["file_path", "new_content"]
                }
        """
        self.tools[name] = func
        self.tool_schemas[name] = {
            "description": description or func.__doc__ or name,
            "parameters": parameters or self._infer_params(func),
        }

    def get_openai_tools(self) -> list[dict]:
        """返回 OpenAI function calling 格式的 tools 列表，可直接传入 litellm"""
        result = []
        for name, schema in self.tool_schemas.items():
            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            })
        return result

    def execute_tool(self, name: str, arguments: dict | str) -> str:
        """执行指定工具并返回结果字符串

        Args:
            name: 工具名称
            arguments: 工具参数，可以是 dict 或 JSON 字符串
        """
        func = self.tools.get(name)
        if not func:
            return f"[Error] Tool '{name}' not found"

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments: {arguments}"

        try:
            result = func(**arguments)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"[Error] Execution failed: {e}"

    # ---- 内置工具：文件操作 ----

    def edit_file(self, file_path: str, new_content: str):
        """编辑（覆盖写入）文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"File saved: {file_path}"
        except Exception as e:
            return f"Error editing file {file_path}: {e}"

    def read_file(self, file_path: str) -> str:
        """读取文件内容"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

    # ---- 内置工具：桌宠状态控制 ----

    def emit_pet_action(self, action: str):
        """触发桌宠的动画/表情状态切换（通过事件总线通知前端）"""
        # TODO: 接入实际的事件推送机制（如 WebSocket / asyncio.Queue）
        # 暂时只返回确认文本，前端推送逻辑后续补充
        return f"已触发桌宠动作: {action}"

    def setup_builtin_tools(self):
        """注册内置的文件读写工具 + 桌宠控制工具"""
        self.register_tool(
            name="edit_file",
            func=self.edit_file,
            description="编辑或创建文件，将内容写入指定路径",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要编辑的文件路径",
                    },
                    "new_content": {
                        "type": "string",
                        "description": "要写入的新内容",
                    },
                },
                "required": ["file_path", "new_content"],
            },
        )
        self.register_tool(
            name="read_file",
            func=self.read_file,
            description="读取指定路径的文件内容",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件路径",
                    },
                },
                "required": ["file_path"],
            },
        )
        self.register_tool(
            name="emit_pet_action",
            func=self.emit_pet_action,
            description="触发桌宠做出特定动作或表情反应，比如开心、思考、挥手、跳跃",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["happy", "thinking", "waving", "jumping", "idle"],
                        "description": "要触发的动作类型",
                    }
                },
                "required": ["action"],
            },
        )

    # ---- 私有辅助 ----

    @staticmethod
    def _infer_params(func: Callable) -> dict:
        """从函数签名简单推断参数 schema（无注解时默认 string）"""
        import inspect

        sig = inspect.signature(func)
        properties = {}
        required = []
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            properties[pname] = {"type": "string", "description": pname}
            if param.default is inspect.Parameter.empty:
                required.append(pname)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        return schema


if __name__ == "__main__":
    tk = NativeToolkit()
    tk.setup_builtin_tools()

    # 查看生成的 OpenAI tools 格式
    print(json.dumps(tk.get_openai_tools(), indent=2, ensure_ascii=False))

    # 执行工具
    result = tk.execute_tool("read_file", {"file_path": "test.txt"})
    print(f"read_file result: {result}")