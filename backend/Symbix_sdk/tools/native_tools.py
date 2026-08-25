from __future__ import annotations
from typing import Callable, Any
import json
import inspect
import os

class NativeToolkit:
    """本地原生工具包 - 注册、管理和执行本地 Python 函数工具"""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.tool_schemas: dict[str, dict] = {}
        self._skill_registry = None  # 关联的 SkillRegistry，用于注册 skill 为工具
        self._skill_tool_names: set[str] = set()  # 追踪哪些工具名来自 skill

    # ---- Skill 注册管理 ----

    def set_skill_registry(self, registry):
        """关联 SkillRegistry，把每个已加载 skill 注册为可调用工具"""
        self._skill_registry = registry
        self.register_skill_tools()

    def register_skill_tools(self):
        """把所有已加载的 skill 注册为 native 工具
        每个工具名为 'skill__<skill_name>'，调用后返回该 skill 的完整 SKILL.md 内容
        """
        if not self._skill_registry:
            return
        self._skill_tool_names.clear()
        for skill in self._skill_registry.list():
            tool_name = f"skill__{skill.name}"
            self._skill_tool_names.add(tool_name)
            # 避免重复注册
            if tool_name in self.tools:
                continue
            description = (skill.description or skill.display_name or skill.name)[:200]
            full_desc = (
                f"加载并返回名为 '{skill.display_name or skill.name}' 的技能指南。"
                f"当用户的请求与该技能相关时调用此工具以获取完整技能说明。"
                f"简介: {description}"
            )
            self.tools[tool_name] = self._make_skill_executor(skill.name)
            self.tool_schemas[tool_name] = {
                "description": full_desc,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }

    def _make_skill_executor(self, skill_name: str) -> Callable:
        """生成一个执行函数：返回指定 skill 的完整 SKILL.md 内容"""
        def _execute(**kwargs):
            if not self._skill_registry:
                return "[Error] SkillRegistry not attached"
            skill = self._skill_registry.get(skill_name)
            if not skill:
                return f"[Error] Skill '{skill_name}' not found"
            return skill.skill_md_content
        _execute.__name__ = f"skill__{skill_name}"
        return _execute

    # ---- 工具注册 ----

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
            parameters: 参数 JSON Schema
        """
        self.tools[name] = func
        self.tool_schemas[name] = {
            "description": description or func.__doc__ or name,
            "parameters": parameters or self._infer_params(func),
        }

    def setup_builtin_tools(self):
        """注册所有内置工具（委托给 tool_setup.py）"""
        from Symbix_sdk.tools.tool_setup import setup_builtin_tools
        setup_builtin_tools(self)

    # ---- 向后兼容：将未定义属性自动委托给同名注册工具 ----
    # 测试和老代码可能直接调用 toolkit.list_files() / toolkit.read_file() 等

    def __getattr__(self, name: str):
        """将缺失的属性访问委托给已注册的工具函数。

        例如 toolkit.list_files(directory='.') → execute_tool('list_files', {...})
        这样可以保持向后兼容：老代码不用改导入路径，新代码也可以用 tool_setup 注册。
        """
        # 防止 __init__ 阶段递归
        if name.startswith("_"):
            raise AttributeError(name)
        func = self.tools.get(name)
        if func is not None:
            def _wrapper(**kwargs):
                return self.execute_tool(name, kwargs)
            return _wrapper
        raise AttributeError(
            f"'NativeToolkit' object has no attribute '{name}' "
            f"(not a registered tool). Available: {sorted(self.tools.keys())}"
        )

    # 显式方法依然保留（加速常用路径）:
    def create_skill(self, **kwargs) -> str:
        """委托给注册好的 create_skill 工具"""
        return self.execute_tool("create_skill", kwargs)

    def open_terminal(self, **kwargs) -> str:
        """委托给注册好的 open_terminal 工具"""
        return self.execute_tool("open_terminal", kwargs)

    # ---- 导出（给 registry / LLM 调用）----

    def get_openai_tools(self) -> list[dict]:
        """返回 OpenAI function calling 格式的 tools 列表（含 native + skill），可直接传入 litellm"""
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

    def get_native_only_tools(self) -> list[dict]:
        """返回仅原生内置工具（排除 skill__ 前缀的工具）"""
        result = []
        for name, schema in self.tool_schemas.items():
            if name in self._skill_tool_names:
                continue
            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            })
        return result

    def get_skill_tools(self) -> list[dict]:
        """返回仅 skill 工具（skill__ 前缀），附上对应的 skill 名称/描述"""
        result = []
        for name in sorted(self._skill_tool_names):
            schema = self.tool_schemas.get(name)
            if not schema:
                continue
            skill_name = name[len("skill__"):]
            skill_info = None
            if self._skill_registry:
                skill_info = self._skill_registry.get(skill_name)
            result.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
                # 额外元数据，方便前端关联展示
                "_skill_name": skill_name,
                "_skill_display": skill_info.display_name if skill_info else skill_name,
                "_skill_description": skill_info.description if skill_info else "",
            })
        return result

    # ---- 工具执行 ----

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

        if not isinstance(arguments, dict):
            return f"[Error] Invalid arguments for tool '{name}': expected a JSON object"

        try:
            sig = inspect.signature(func)
            accepts_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if not accepts_kwargs:
                allowed = set(sig.parameters)
                unknown = sorted(set(arguments) - allowed)
                if unknown:
                    return (
                        f"[Error] Unsupported arguments for tool '{name}': {unknown}. "
                        f"Supported arguments: {sorted(allowed)}. "
                        "Please retry with only supported arguments."
                    )
            result = func(**arguments)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"[Error] Execution failed: {e}"

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


# ---------------------------------------------------------------------------
# 向后兼容的 <if __name__ == '__main__'> 测试
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    # 确保模块路径正确
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    tk = NativeToolkit()
    tk.setup_builtin_tools()

    # 查看生成的 OpenAI tools 格式
    print(json.dumps(tk.get_openai_tools(), indent=2, ensure_ascii=False))

    # 执行工具
    result = tk.execute_tool("read_file", {"file_path": "test.txt"})
    print(f"read_file result: {result}")