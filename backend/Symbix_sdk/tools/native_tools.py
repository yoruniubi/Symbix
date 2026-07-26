# tools/native_tools.py
"""
本地原生工具包
负责注册、管理和执行运行在本应用进程内部的 Python 函数工具
（例如：文件读写、桌宠状态控制、skill 创建等），与外部 MCP server 区分开
"""
from __future__ import annotations
from typing import Callable, Any
import json
import os
import re

from Symbix_sdk.tools.file_pipeline import assert_path_allowed, resolve_under_allowed


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
            path = assert_path_allowed(file_path)
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return f"File saved: {path}"
        except Exception as e:
            return f"Error editing file {file_path}: {e}"

    def list_files(self, directory: str = ".", recursive: bool = False) -> str:
        """列出指定目录下的文件和子目录"""
        import os
        try:
            directory = assert_path_allowed(directory)
            entries = []
            if recursive:
                for root, dirs, files in os.walk(directory):
                    rel = os.path.relpath(root, directory)
                    prefix = "" if rel == "." else rel + "/"
                    for d in dirs:
                        entries.append(f"{prefix}{d}/")
                    for f in files:
                        entries.append(f"{prefix}{f}")
            else:
                for name in os.listdir(directory):
                    full = os.path.join(directory, name)
                    if os.path.isdir(full):
                        entries.append(f"{name}/")
                    else:
                        entries.append(name)
            result = "\n".join(sorted(entries)) if entries else "(empty)"
            return result
        except Exception as e:
            return f"Error listing directory {directory}: {e}"

    def read_file(self, file_path: str) -> str:
        """读取文件内容"""
        try:
            path = assert_path_allowed(file_path)
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file {file_path}: {e}"

    def parse_file(self, file_path: str, max_chars: int = 50000) -> str:
        """结构化解析文件（txt/md/json/csv/pdf/docx/图片元信息），返回可读文本摘要。"""
        from Symbix_sdk.tools.file_pipeline import parse_file_path

        try:
            max_chars = int(max_chars) if max_chars is not None else 50000
        except (TypeError, ValueError):
            max_chars = 50000
        max_chars = max(500, min(max_chars, 200_000))

        try:
            parsed = parse_file_path(
                file_path,
                max_chars=max_chars,
                include_image_base64=False,
            )
            if parsed.get("status") != "ok":
                return parsed.get("message") or f"Error parsing {file_path}"
            kind = parsed.get("kind") or "file"
            name = parsed.get("filename") or file_path
            path = parsed.get("path") or file_path
            body = parsed.get("text") or ""
            size = parsed.get("size")
            header = f"[{kind}] {name} ({size} bytes)\npath: {path}\n"
            return header + body
        except Exception as e:
            return f"Error parsing file {file_path}: {e}"

    # ---- 内置工具：桌宠状态控制 ----

    # 与 spritesheet / 前端 Home.vue 对齐；语义别名会在总线侧归一化
    PET_ACTION_ENUM = [
        "idle",
        "waving",
        "jumping",
        "failed",
        "waiting",
        "review",
        "running",
        "runningRight",
        "runningLeft",
        "happy",      # → jumping
        "thinking",   # → review
        "sad",        # → failed
        "celebrate",  # → jumping
        "wave",       # → waving
        "jump",       # → jumping
        "error",      # → failed
    ]

    def emit_pet_action(self, action: str, bubble: str = "") -> str:
        """触发桌宠动画/表情，经事件总线推送到 Home 窗口 SSE。

        Args:
            action: 动作名（见 PET_ACTION_ENUM；别名会映射到真实 spritesheet 行）
            bubble: 可选气泡文案（前端显示约 3 秒）
        """
        action = (action or "").strip()
        if not action:
            return json.dumps(
                {"status": "error", "message": "action 不能为空"},
                ensure_ascii=False,
            )

        try:
            # application 层事件总线（backend 进程内可用）
            from application.pet_bus import pet_bus, normalize_pet_action

            event = pet_bus.emit(
                action,
                bubble=bubble or "",
                source="emit_pet_action",
            )
            normalized = event.get("action") or normalize_pet_action(action)
            return json.dumps(
                {
                    "status": "ok",
                    "action": normalized,
                    "raw_action": action,
                    "bubble": event.get("bubble") or "",
                    "id": event.get("id"),
                    "subscribers": "sse:/pet/events",
                    "message": f"已触发桌宠动作: {normalized}"
                    + (f"（气泡: {event['bubble']}）" if event.get("bubble") else ""),
                },
                ensure_ascii=False,
            )
        except Exception as e:
            # 无 application 上下文时仍返回可解析结果，便于单测
            return json.dumps(
                {
                    "status": "queued_local",
                    "action": action,
                    "bubble": (bubble or "").strip(),
                    "message": f"已记录桌宠动作: {action}（事件总线不可用: {e}）",
                },
                ensure_ascii=False,
            )


    # ---- 内置工具：Skill 创建 ----

    # 默认 skill 安装目录（相对于本文件）
    _DEFAULT_SKILLS_DIR = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "skill", "installed_skill")
    )

    SKILL_MD_TEMPLATE = """---
name: {skill_name}
description: {description}
---

# {display_name}

## When to use this skill

- "{trigger_1}"
- "{trigger_2}"

## Purpose

{purpose}

## Instructions

{instructions}
"""

    @staticmethod
    def _slugify_skill_name(name: str) -> str:
        """将名称规范为英文小写 + 连字符的 skill 标识"""
        if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
            return name
        result = re.sub(r"[\s_]+", "-", name.lower())
        result = re.sub(r"[^a-z0-9-]", "", result)
        return result.strip("-") or name

    def _resolve_skills_dir(self) -> str:
        """解析 skill 安装目录：优先用 SkillRegistry，否则用默认路径"""
        if self._skill_registry and getattr(self._skill_registry, "skills_dir", None):
            return os.path.abspath(self._skill_registry.skills_dir)
        return os.path.abspath(self._DEFAULT_SKILLS_DIR)

    def create_skill(
        self,
        skill_name: str,
        description: str,
        display_name: str = "",
        purpose: str = "",
        instructions: str = "",
        skill_md_content: str = "",
        reload: bool = True,
    ) -> str:
        """在 installed_skill/ 下创建完整 skill 骨架（类似 MCP installer）

        优先委托 skill-creator/scripts/init_skill.py 的 create_skill_skeleton，
        保证 CLI 与 native tool 使用同一套模板逻辑。

        目录结构:
            installed_skill/<skill_name>/
            ├── SKILL.md
            ├── agents/
            ├── scripts/
            ├── references/
            └── assets/

        Args:
            skill_name: skill 标识（英文小写+连字符）
            description: 简短描述（用于触发匹配，写入 frontmatter）
            display_name: 显示名称（中文友好名）
            purpose: 技能目的说明
            instructions: 给 agent 的操作指令
            skill_md_content: 若提供则直接作为完整 SKILL.md 内容（覆盖模板）
            reload: 创建后是否立即重新扫描并注册 skill

        Returns:
            JSON 字符串，含 status / path / skill_name / message
        """
        try:
            skill_slug = self._slugify_skill_name((skill_name or "").strip())
            if not skill_slug:
                return json.dumps(
                    {"status": "error", "message": "skill_name 不能为空"},
                    ensure_ascii=False,
                )
            if not description or not str(description).strip():
                return json.dumps(
                    {"status": "error", "message": "description 不能为空（用于触发匹配）"},
                    ensure_ascii=False,
                )

            skills_dir = self._resolve_skills_dir()
            result = self._run_create_skill_skeleton(
                skill_slug=skill_slug,
                description=str(description).strip(),
                display_name=(display_name or skill_name or skill_slug).strip(),
                purpose=purpose or "",
                instructions=instructions or "",
                skill_md_content=skill_md_content or "",
                target_dir=skills_dir,
            )
            if not result.get("ok"):
                return json.dumps(
                    {
                        "status": "error",
                        "skill_name": skill_slug,
                        "path": result.get("path") or "",
                        "message": result.get("error") or "创建 skill 失败",
                    },
                    ensure_ascii=False,
                )

            skill_dir = result["path"]
            skill_md_path = result["skill_md"]
            reloaded = False
            reload_error = None
            if reload and self._skill_registry is not None:
                try:
                    self._skill_registry.scan()
                    self.register_skill_tools()
                    reloaded = True
                except Exception as e:
                    reload_error = str(e)

            message = result.get("message") or f"Skill 骨架已创建: {skill_dir}"
            message += (
                "\n下一步: 编辑 SKILL.md 完善指令；"
                "需要时可在 agents/、scripts/、references/、assets/ 中补充资源。"
            )
            if reloaded:
                message += f" 已热加载并注册为 skill__{skill_slug} 工具。"
            elif reload_error:
                message += (
                    f" 但热加载失败: {reload_error}。"
                    "请调用 /skills/reload 或重启服务。"
                )

            return json.dumps(
                {
                    "status": "ok",
                    "skill_name": skill_slug,
                    "path": os.path.abspath(skill_dir),
                    "skill_md": os.path.abspath(skill_md_path) if skill_md_path else "",
                    "created": result.get("created") or [],
                    "reloaded": reloaded,
                    "message": message,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"创建 skill 失败: {e}"},
                ensure_ascii=False,
            )

    def _run_create_skill_skeleton(
        self,
        skill_slug: str,
        description: str,
        display_name: str,
        purpose: str,
        instructions: str,
        skill_md_content: str,
        target_dir: str,
    ) -> dict:
        """调用 init_skill.create_skill_skeleton（通过 importlib 加载含连字符路径的模块）；
        加载失败时回退到内置实现。"""
        try:
            import importlib.util

            # 本文件位于 tools/，目标脚本在 skill/installed_skill/skill-creator/scripts/init_skill.py
            _TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
            init_path = os.path.join(
                _TOOLS_DIR, "..", "skill", "installed_skill", "skill-creator", "scripts", "init_skill.py"
            )
            init_path = os.path.normpath(init_path)
            if os.path.isfile(init_path):
                spec = importlib.util.spec_from_file_location("symbix_init_skill", init_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    return mod.create_skill_skeleton(
                        skill_name=skill_slug,
                        description=description,
                        display_name=display_name,
                        purpose=purpose,
                        instructions=instructions,
                        skill_md_content=skill_md_content,
                        target_dir=target_dir,
                        overwrite=False,
                    )
            raise FileNotFoundError(f"init_skill.py not found at {init_path}")
        except Exception as e:
            return self._fallback_create_skill_skeleton(
                skill_slug=skill_slug,
                description=description,
                display_name=display_name,
                purpose=purpose,
                instructions=instructions,
                skill_md_content=skill_md_content,
                target_dir=target_dir,
                import_error=str(e),
            )

    def _fallback_create_skill_skeleton(
        self,
        skill_slug: str,
        description: str,
        display_name: str,
        purpose: str,
        instructions: str,
        skill_md_content: str,
        target_dir: str,
        import_error: str = "",
    ) -> dict:
        """init_skill 不可用时的内置骨架创建逻辑。"""
        skill_dir = os.path.join(os.path.abspath(target_dir), skill_slug)
        if os.path.exists(os.path.join(skill_dir, "SKILL.md")):
            return {
                "ok": False,
                "skill_name": skill_slug,
                "path": skill_dir,
                "skill_md": "",
                "created": [],
                "message": "",
                "error": (
                    f"Skill 已存在: {skill_dir}。"
                    "如需修改请直接编辑 SKILL.md，或先删除后重建。"
                ),
            }

        created: list[str] = []
        os.makedirs(skill_dir, exist_ok=True)
        created.append(skill_dir)
        for sub in ("agents", "scripts", "references", "assets"):
            sub_path = os.path.join(skill_dir, sub)
            os.makedirs(sub_path, exist_ok=True)
            created.append(sub_path)

        if skill_md_content and skill_md_content.strip():
            content = skill_md_content.strip() + "\n"
            if not content.lstrip().startswith("---"):
                content = (
                    f"---\nname: {skill_slug}\ndescription: {description}\n---\n\n"
                    + content
                )
        else:
            purpose_text = purpose or (
                f"这个技能用于处理 {display_name} 相关的任务，帮助 agent 更高效地完成工作。"
            )
            instructions_text = instructions or (
                "1. 理解用户的需求和目标\n"
                "2. 根据 skill 的指引执行相应操作\n"
                "3. 向用户确认结果是否符合预期\n"
            )
            content = self.SKILL_MD_TEMPLATE.format(
                skill_name=skill_slug,
                description=description.strip(),
                display_name=display_name,
                trigger_1="用户提到相关需求时",
                trigger_2="当需要执行相关任务时",
                purpose=purpose_text,
                instructions=instructions_text,
            )

        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md_path, "w", encoding="utf-8") as f:
            f.write(content)
        created.append(skill_md_path)

        msg = f"Skill '{skill_slug}' 骨架已创建于 {skill_dir}"
        if import_error:
            msg += f"（init_skill 导入失败，已用内置模板: {import_error}）"

        return {
            "ok": True,
            "skill_name": skill_slug,
            "path": skill_dir,
            "skill_md": skill_md_path,
            "created": created,
            "message": msg,
            "error": None,
        }

    # ---- 内置工具：终端命令执行 ----

    def open_terminal(
        self,
        command: str,
        shell: str = "powershell",
        working_directory: str = ".",
        timeout: int = 60,
    ) -> str:
        """在 PowerShell 或 CMD 中执行命令，并返回 stdout/stderr。"""
        import subprocess

        shell = (shell or "powershell").strip().lower()
        cwd = working_directory or "."
        try:
            cwd = assert_path_allowed(cwd)
        except Exception as e:
            return f"[Error] working_directory 不允许: {e}"
        if not os.path.isdir(cwd):
            return f"[Error] working_directory 不存在: {cwd}"

        try:
            timeout = int(timeout) if timeout is not None else 60
        except (TypeError, ValueError):
            timeout = 60
        timeout = max(1, min(timeout, 300))  # 限制 1–300 秒

        if shell in ("powershell", "pwsh", "ps"):
            shell_cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]
        elif shell in ("cmd", "command", "cmd.exe"):
            shell_cmd = ["cmd", "/c", command]
        else:
            return f"[Error] 不支持的 shell: {shell}。请使用 'powershell' 或 'cmd'。"

        try:
            proc = subprocess.run(
                shell_cmd,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            parts = []
            if proc.stdout and proc.stdout.strip():
                parts.append(proc.stdout.rstrip())
            if proc.stderr and proc.stderr.strip():
                parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
            parts.append(f"[exit_code={proc.returncode}]")
            return "\n".join(parts)
        except subprocess.TimeoutExpired:
            return f"[Error] 命令超时（>{timeout}s）: {command}"
        except FileNotFoundError as e:
            return f"[Error] 找不到 shell 可执行文件: {e}"
        except Exception as e:
            return f"[Error] 执行失败: {e}"

    def setup_builtin_tools(self):
        """注册内置的文件读写工具、桌宠控制、终端 + create_skill 工具"""
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
            name="list_files",
            func=self.list_files,
            description="列出指定目录下的文件和文件夹。如果不知道要读什么文件，先调用此工具浏览目录结构。工作目录是 F:\\Symbix，源代码在 backend/ 和 Symbix_frontend/ 中。",
            parameters={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "要浏览的目录路径，默认为当前工作目录 (F:\\Symbix)",
                        "default": ".",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出所有子目录和文件，默认为 false",
                        "default": False,
                    },
                },
                "required": [],
            },
        )
        self.register_tool(
            name="read_file",
            func=self.read_file,
            description="读取指定路径的文件内容。先用 list_files 浏览目录结构确定文件路径，再用本工具读取。工作目录是 F:\\Symbix。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "要读取的文件路径（相对于工作目录 F:\\Symbix 的路径或绝对路径）",
                    },
                },
                "required": ["file_path"],
            },
        )
        self.register_tool(
            name="parse_file",
            func=self.parse_file,
            description=(
                "结构化解析本地/上传文件内容并返回文本摘要。"
                "支持 txt/md/json/csv/代码、PDF、DOCX、图片元信息。"
                "用户附件路径一般在 backend/uploads/<session_id>/ 下；"
                "比 read_file 更适合 PDF/表格/二进制文档。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件绝对路径或工作区内路径（上传接口返回的 path 可直接使用）",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "返回文本最大字符数，默认 50000",
                        "default": 50000,
                    },
                },
                "required": ["file_path"],
            },
        )
        self.register_tool(
            name="emit_pet_action",
            func=self.emit_pet_action,
            description=(
                "触发桌宠动画/表情并推送到主窗口。"
                "在对话中表达情绪、完成任务庆祝、失败遗憾、思考中、打招呼时调用。"
                "可用动作: idle/waving/jumping/failed/waiting/review/running，"
                "以及别名 happy→jumping、thinking→review、sad/error→failed、celebrate→jumping。"
                "可选 bubble 显示短气泡文案。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(self.PET_ACTION_ENUM),
                        "description": (
                            "动作类型。优先用真实动作名；"
                            "happy/thinking/sad/celebrate 等别名会自动映射。"
                        ),
                    },
                    "bubble": {
                        "type": "string",
                        "description": "可选：桌宠头顶短气泡（中文，≤40字）",
                    },
                },
                "required": ["action"],
            },
        )

        self.register_tool(
            name="open_terminal",
            func=self.open_terminal,
            description="用于让agent打开powershell或者是cmd来执行命令",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要在终端中执行的命令。如果为空则只打开终端。",
                    },
                    "shell": {
                        "type": "string",
                        "enum": ["powershell", "cmd"],
                        "description": "终端类型",
                    },
                    "working_directory": {
                        "type": "string",
                        "description": "工作目录，默认为当前目录",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "命令超时时间（秒），默认 60，最大 300",
                    },
                },
                "required": [],
            },
        )
        self.register_tool(
            name="create_skill",
            func=self.create_skill,
            description=(
                "创建新的 Agent Skill 骨架，写入 installed_skill/<skill_name>/ 目录。"
                "当用户要求创建 skill、生成技能模板、或 skill-creator 工作流需要初始化目录时调用。"
                "会自动生成 SKILL.md（含 frontmatter）以及 agents/、scripts/、references/、assets/ 子目录，"
                "并在创建后热加载注册。请勿在其他路径手动创建 skill。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "Skill 标识名（英文小写+连字符，如 pdf-helper、code-reviewer）",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Skill 简短描述，写入 frontmatter，用于触发匹配。"
                            "应说明做什么、何时触发（WHAT + WHEN），第三人称。"
                        ),
                    },
                    "display_name": {
                        "type": "string",
                        "description": "显示名称（中文友好名），可选，默认等于 skill_name",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "技能目的说明（写入 SKILL.md 的 Purpose 段落），可选",
                    },
                    "instructions": {
                        "type": "string",
                        "description": "给 agent 的操作指令正文（写入 SKILL.md 的 Instructions），可选",
                    },
                    "skill_md_content": {
                        "type": "string",
                        "description": (
                            "完整的 SKILL.md 内容。若提供则覆盖模板生成；"
                            "若无 frontmatter 会自动补上 name/description。"
                        ),
                    },
                    "reload": {
                        "type": "boolean",
                        "description": "创建后是否立即重新扫描并注册 skill，默认 true",
                        "default": True,
                    },
                },
                "required": ["skill_name", "description"],
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