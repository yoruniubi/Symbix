from typing import Tuple, Union, Optional
import os
import re
import json

class ToolRiskLevel:
    """风险等级常量"""
    SAFE = "safe"        # 只读操作，直接放行
    MEDIUM = "medium"    # 写入/修改操作，需审批
    HIGH = "high"        # 删除/执行命令，强制审批+警告


# ============ override 持久化 ============
_OVERRIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "risk_overrides.json",
)

_override_cache: Optional[dict] = None


def _load_overrides() -> dict:
    """加载 override 配置（{tool_name: {"level": "safe|medium|high", "reason": "..."}}）。"""
    global _override_cache
    if _override_cache is not None:
        return _override_cache
    if not os.path.exists(_OVERRIDE_PATH):
        _override_cache = {}
        return _override_cache
    try:
        with open(_OVERRIDE_PATH, "r", encoding="utf-8") as f:
            _override_cache = json.load(f) or {}
    except Exception:
        _override_cache = {}
    return _override_cache


def _save_overrides(data: dict) -> None:
    global _override_cache
    _override_cache = data
    os.makedirs(os.path.dirname(_OVERRIDE_PATH), exist_ok=True)
    with open(_OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_overrides() -> dict:
    """返回当前 override 配置（深拷贝，避免外部误改缓存）。"""
    return json.loads(json.dumps(_load_overrides()))


def set_override(tool_name: str, level: str, reason: str = "") -> None:
    """新增/更新一条 override。level 必须是 safe/medium/high。"""
    if level not in (ToolRiskLevel.SAFE, ToolRiskLevel.MEDIUM, ToolRiskLevel.HIGH):
        raise ValueError(f"invalid level: {level}")
    data = _load_overrides()
    data[tool_name] = {"level": level, "reason": reason or f"自定义分级: {level}"}
    _save_overrides(data)


def remove_override(tool_name: str) -> bool:
    """删除一条 override，恢复默认。返回是否确实删了一条。"""
    data = _load_overrides()
    if tool_name in data:
        del data[tool_name]
        _save_overrides(data)
        return True
    return False


# ============ 默认规则（代码内 ground truth）============

_READONLY_TOOLS = {
    "read_file", "list_files", "search_files", "parse_file",
    "read_multiple_files", "get_file_info", "search_codebase",
    "search_file_with_name",
    "emit_pet_action", "check_agent_status", "play_status_animation",
}

_WRITE_TOOLS = {
    "edit_file", "write_to_file", "replace_in_file",
    "search_and_replace",
    "create_skill", "create_directory", "move_file",
}

_DANGEROUS_CMD_PATTERNS = [
    r"rm\s+-rf", r"dd\s+if=", r"mkfs", r">/dev/",
    r"format", r"del\s+/s", r"shutdown", r"reboot", r"chmod\s+777",
]

_CRITICAL_FILE_PATTERNS = [".env", "config", "database", ".db", "credentials", "secret"]
_CRITICAL_PATHS = ["/etc/", "/sys/", "/proc/", "C:\\Windows\\", "C:\\Program Files\\"]


def _classify_default(tool_name: str, arguments: dict) -> Tuple[str, str]:
    """代码内默认分级逻辑（不可被前端删除）。"""
    if tool_name in _READONLY_TOOLS:
        return (ToolRiskLevel.SAFE, "只读/无副作用操作，安全放行")

    if tool_name == "delete_file":
        path = arguments.get("file_path", "")
        if any(p in path.lower() for p in _CRITICAL_FILE_PATTERNS):
            return (ToolRiskLevel.HIGH, f"删除关键文件: {path}")
        return (ToolRiskLevel.HIGH, "删除文件操作")

    if tool_name in ("run_command", "execute_command", "exec_command"):
        cmd = arguments.get("command", "")
        for p in _DANGEROUS_CMD_PATTERNS:
            if re.search(p, cmd.lower()):
                return (ToolRiskLevel.HIGH, f"危险命令: {cmd[:50]}")
        return (ToolRiskLevel.MEDIUM, "执行命令")

    if tool_name == "open_terminal":
        cmd = arguments.get("command", "") or ""
        if cmd.strip():
            for p in _DANGEROUS_CMD_PATTERNS:
                if re.search(p, cmd.lower()):
                    return (ToolRiskLevel.HIGH, f"危险命令 (open_terminal): {cmd[:50]}")
            return (ToolRiskLevel.MEDIUM, "通过 open_terminal 执行命令")
        return (ToolRiskLevel.MEDIUM, "打开终端窗口")

    if tool_name in ("write_file", "write_to_file", "create_file", "edit_file", "search_and_replace"):
        path = arguments.get("file_path", arguments.get("path", ""))
        if any(path.startswith(cp) for cp in _CRITICAL_PATHS):
            return (ToolRiskLevel.HIGH, f"写入系统关键路径: {path}")

    if tool_name in _WRITE_TOOLS:
        return (ToolRiskLevel.MEDIUM, "文件修改操作")

    return (ToolRiskLevel.MEDIUM, "未分类工具，建议审查")


def classify_tool_risk(tool_name: str, arguments: Union[dict, str]) -> Tuple[str, str]:
    """
    分析工具调用的风险等级。override 优先于默认。

    Args:
        tool_name: 工具名称
        arguments: 工具参数字典或JSON字符串

    Returns:
        (risk_level, reason) 元组
    """
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}

    # override 优先：前端显式配置的工具直接用 override 等级
    overrides = _load_overrides()
    ov = overrides.get(tool_name)
    if ov:
        return (ov.get("level", ToolRiskLevel.MEDIUM), ov.get("reason", "自定义分级"))

    return _classify_default(tool_name, arguments)


def get_effective_rules() -> dict:
    """返回合并后的生效规则（默认 + override），供前端展示。

    结构：{tool_name: {"level": str, "reason": str, "source": "default"|"override"}}
    """
    overrides = _load_overrides()
    # 从默认逻辑反推已知工具的"基础等级"（不含参数敏感的 HIGH 升级，只取工具默认档）
    known: dict = {}
    for t in _READONLY_TOOLS:
        known[t] = (ToolRiskLevel.SAFE, "只读/无副作用操作，安全放行")
    for t in _WRITE_TOOLS:
        known[t] = (ToolRiskLevel.MEDIUM, "文件修改操作")
    for t in ("delete_file",):
        known[t] = (ToolRiskLevel.HIGH, "删除文件操作")
    for t in ("run_command", "execute_command", "exec_command", "open_terminal"):
        known[t] = (ToolRiskLevel.MEDIUM, "执行命令/打开终端")

    result: dict = {}
    for t, (lvl, reason) in known.items():
        if t in overrides:
            result[t] = {"level": overrides[t]["level"], "reason": overrides[t].get("reason", ""), "source": "override"}
        else:
            result[t] = {"level": lvl, "reason": reason, "source": "default"}
    # override 里可能有默认规则未覆盖的工具名
    for t, ov in overrides.items():
        if t not in result:
            result[t] = {"level": ov["level"], "reason": ov.get("reason", ""), "source": "override"}
    return result


# 测试代码
if __name__ == "__main__":
    test_cases = [
        ("read_file", {"file_path": "test.txt"}),
        ("delete_file", {"file_path": ".env"}),
        ("delete_file", {"file_path": "temp.log"}),
        ("run_command", {"command": "rm -rf /"}),
        ("run_command", {"command": "ls -la"}),
        ("edit_file", {"file_path": "code.py", "content": "print('hello')"}),
        ("search_file_with_name", {"file_name": "main.py"}),
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "./src.py"}),
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "C:\\Windows\\System32\\x.cfg"}),
        ("open_terminal", {"visible": True}),
        ("open_terminal", {"command": "rm -rf /", "visible": False}),
        ("open_terminal", {"command": "git status", "visible": False}),
    ]

    print("风险分级测试:")
    for tool_name, args in test_cases:
        level, reason = classify_tool_risk(tool_name, args)
        print(f"  {tool_name}: {level.upper()} - {reason}")
