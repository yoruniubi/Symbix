from __future__ import annotations
from typing import Callable, Any
import asyncio
import json
import inspect
import os

from . import skill_files

class NativeToolkit:
    """本地原生工具包 - 注册、管理和执行本地 Python 函数工具"""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self.tool_schemas: dict[str, dict] = {}
        self._skill_registry = None  # 关联的 SkillRegistry，用于注册 skill 为工具
        self._skill_tool_names: set[str] = set()  # 追踪哪些工具名来自 skill

    def set_skill_registry(self, registry):
        """关联 SkillRegistry，把每个已加载 skill 注册为可调用工具"""
        self._skill_registry = registry
        self.register_skill_tools()

    def register_skill_tools(self):
        """把所有已加载的 skill 注册为 native 工具

        工具名为 'skill__<skill_name>':
          - 无参数 → 返回 SKILL.md 全文 + 技能目录文件清单(清单/摘要由 skill_files 生成)
          - paths=[...] → 批量读取技能内文件(避免模型逐个 read_file 猜路径)
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
                f"加载名为 '{skill.display_name or skill.name}' 的技能指南(SKILL.md 全文)与技能目录文件清单。"
                "当用户的请求可能与该技能相关时,**主动调用此工具**获取完整指南,"
                "并严格按指南中的步骤与指令执行,不要只凭本简介推测做法。"
                "\n四种用法(按需选):"
                "① 不带参数 → SKILL.md 全文 + 文件清单(大小/一行摘要,SKILL.md 提到过的路径带 `*`);"
                "② search=\"关键词A 关键词B\" → 在技能内检索(多个关键词任一命中即算),"
                "返回 `文件:行号 [所属标题]` + 命中行与上下文,**先检索定位再精读,最省 token**;"
                "③ section=\"标题\"(可配 paths,默认 SKILL.md)→ 只读这一节;"
                "④ paths=[\"references/a.md\", \"config/b.json#配色\", \"c.md:100-180\"] → 一次读多个文件,"
                "路径可带 `#标题`(只读该节)或 `:起-止行` 定位后缀。"
                "单文件太大被截断时用 offset=<原文件行号> 续读。"
                "\n注意:不要用 read_file 去猜技能目录里的路径;文件多时先用 ② 定位,再用 ③/④ 精读。"
                f"简介: {description}"
            )
            self.tools[tool_name] = self._make_skill_executor(skill.name)
            self.tool_schemas[tool_name] = {
                "description": full_desc,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "要读取的文件或目录(相对 skill 根目录的路径)。可一次传多个;"
                                "路径可带定位后缀:`a.md#标题` 只读该节、`a.md:100-180` 只读行范围;"
                                "传目录名则列出该目录下的文件。search 时作为检索范围。"
                            ),
                        },
                        "search": {
                            "type": "string",
                            "description": (
                                "在技能内检索的关键词。多个关键词用空格分隔(任一命中即算);"
                                "返回 文件名:行号 + 所属标题 + 命中行及上下文"
                            ),
                        },
                        "section": {
                            "type": "string",
                            "description": (
                                "只读取某一个标题下的内容(支持标题部分匹配)。"
                                "默认作用于 SKILL.md,可配合 paths 指定文件;找不到标题时返回该文件标题大纲"
                            ),
                        },
                        "offset": {
                            "type": "integer",
                            "description": "续读起点:从原文件第几行开始(1 起;默认从头读)",
                        },
                        "max_bytes": {
                            "type": "integer",
                            "description": "单个文件最多返回的字节数(默认 24000,上限 200000)",
                        },
                        "context": {
                            "type": "integer",
                            "description": "search 时每个命中行附带的上下行数(默认 1,最大 5)",
                        },
                    },
                    "required": [],
                },
            }

    def _make_skill_executor(self, skill_name: str) -> Callable:
        """生成一个执行函数：返回指定 skill 的完整 SKILL.md 内容"""
        def _execute(paths=None, offset=None, max_bytes=None, search=None,
                     section=None, context=None, **kwargs):
            if not self._skill_registry:
                return "[Error] SkillRegistry not attached"
            skill = self._skill_registry.get(skill_name)
            if not skill:
                return f"[Error] Skill '{skill_name}' not found"
            return self._render_skill(skill, paths=paths, offset=offset, max_bytes=max_bytes,
                                      search=search, section=section, context=context,
                                      extra=kwargs)
        _execute.__name__ = f"skill__{skill_name}"
        return _execute

    def _render_skill(self, skill, paths=None, offset=None, max_bytes=None,
                      search=None, section=None, context=None,
                      extra: dict | None = None) -> str:
        """渲染 skill 工具返回。四种用法(优先级 search > section > paths > 默认):

        1. 无参 → SKILL.md 全文 + 文件清单
        2. search="关键词A 关键词B" → 技能内检索(多词 OR),带所属标题与上下文;
           可配 paths 限定文件范围
        3. section="标题"(可配 paths,默认 SKILL.md)→ 只读这一节
        4. paths=["a.md#标题", "b.md:100-180", "c.py"] → 批量读(可带定位后缀)

        多个模式同时传时不静默:在返回开头写明本次忽略/采用了什么。
        """
        root = (skill.path or "").replace("\\", "/")
        notes: list[str] = []
        keywords = skill_files.normalize_keywords(search)
        sec = (section or "").strip() if isinstance(section, str) else ""
        if not sec and isinstance(section, (list, tuple)) and section:
            sec = str(section[0]).strip()
        wanted = skill_files.normalize_paths(paths)

        if keywords and sec:
            notes.append("[提示] 同时给了 search 与 section,本次只执行 search(结果里的 `[所属标题]` 可直接用于 paths=[\"文件#标题\"])")
            sec = ""
        if keywords and not wanted:
            pass  # 全库检索

        if not root:
            return "\n".join(notes + [skill.skill_md_content])

        header = (
            f"[Skill root] {root}\n"
            "(SKILL.md 里的 `scripts/...`、`references/...`、`assets/...` 等相对路径都相对该目录;"
            "执行命令行时请拼成绝对路径。)\n"
        )
        prefix = ("\n".join(notes) + "\n") if notes else ""

        if keywords:
            body = skill_files.search_files(
                root, keywords,
                context=context if context is not None else skill_files.SEARCH_CONTEXT_DEFAULT,
                only=wanted or None,
            )
            return header + prefix + body

        if sec:
            body = skill_files.read_many(
                root, wanted or ["SKILL.md"], offset=offset or 0,
                max_bytes=max_bytes or skill_files.READ_MAX_BYTES_DEFAULT, section=sec,
            )
            return header + prefix + body

        if wanted:
            body = skill_files.read_many(
                root,
                wanted,
                offset=offset or 0,
                max_bytes=max_bytes or skill_files.READ_MAX_BYTES_DEFAULT,
            )
            return header + prefix + body

        return header + prefix + skill.skill_md_content + "\n\n" + skill_files.build_index(
            root, skill.skill_md_content
        )

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
        """返回 OpenAI function calling 格式的 tools 列表（含 native + skill），可直接发给上游模型"""
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

    def is_async_tool(self, name: str) -> bool:
        """判断某工具是否为 async 函数(如 delegate_task),需 await 执行。

        除普通 async 函数外,也兼容实现了 async __call__ 的可调用对象。
        """
        func = self.tools.get(name)
        if func is None:
            return False
        if asyncio.iscoroutinefunction(func):
            return True
        call = getattr(func, "__call__", None)
        return call is not None and asyncio.iscoroutinefunction(call)

    async def execute_tool_async(
        self,
        name: str,
        arguments: dict | str,
        on_event=None,
        ctx: dict | None = None,
    ) -> str:
        """异步执行工具(同步/异步函数均可),返回结果字符串。

        Args:
            name: 工具名称
            arguments: 工具参数(dict 或 JSON 字符串)
            on_event: 可选异步回调,注入给声明了 `_on_event` 形参的工具(用于进度推送)
            ctx: 可选上下文(如请求级 api_key/model),注入给声明了 `_ctx` 形参的工具

        Returns:
            工具执行结果字符串;失败时返回 `[Error] ...` 文本而非抛异常
        """
        func = self.tools.get(name)
        if not func:
            return f"[Error] Tool '{name}' not found"

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                return f"[Error] Invalid JSON arguments: {arguments}"
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return f"[Error] Invalid arguments for tool '{name}': expected a JSON object"

        try:
            sig = inspect.signature(func)
            params = set(sig.parameters)
            accepts_kwargs = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            # 内部注入形参不由模型提供
            internal = {"_on_event", "_ctx"}
            if not accepts_kwargs:
                allowed = params - internal
                unknown = sorted(set(arguments) - allowed)
                if unknown:
                    return (
                        f"[Error] Unsupported arguments for tool '{name}': {unknown}. "
                        f"Supported arguments: {sorted(allowed)}. "
                        "Please retry with only supported arguments."
                    )
            kwargs = dict(arguments)
            if "_on_event" in params:
                kwargs["_on_event"] = on_event
            if "_ctx" in params:
                kwargs["_ctx"] = ctx
            result = func(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return str(result) if result is not None else ""
        except Exception as e:
            return f"[Error] Execution failed: {e}"

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