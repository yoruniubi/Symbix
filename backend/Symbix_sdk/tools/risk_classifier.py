"""
工具调用风险分级器
根据工具名称和参数动态判断风险等级
"""
from typing import Tuple, Union
import re
import json


class ToolRiskLevel:
    """风险等级常量"""
    SAFE = "safe"        # 只读操作，直接放行
    MEDIUM = "medium"    # 写入/修改操作，需审批
    HIGH = "high"        # 删除/执行命令，强制审批+警告


def classify_tool_risk(tool_name: str, arguments: Union[dict, str]) -> Tuple[str, str]:
    """
    分析工具调用的风险等级
    
    Args:
        tool_name: 工具名称
        arguments: 工具参数字典或JSON字符串
        
    Returns:
        (risk_level, reason) 元组
        - risk_level: "safe" | "medium" | "high"
        - reason: 风险原因说明（中文）
    """
    
    # 如果是字符串，解析为字典
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except (json.JSONDecodeError, ValueError):
            arguments = {}
    
    # 1. 纯读操作 → SAFE
    readonly_tools = {
        "read_file", "list_files", "search_files", "parse_file",
        "read_multiple_files", "get_file_info", "search_codebase",
        "search_file_with_name",  # 只报路径，不读写文件
        # 桌宠动画工具：仅触发 UI 动画/表情，无文件或命令副作用
        "emit_pet_action", "check_agent_status", "play_status_animation",
    }
    if tool_name in readonly_tools:
        return (ToolRiskLevel.SAFE, "只读/无副作用操作，安全放行")
    
    # 2. 高危操作 → HIGH
    if tool_name == "delete_file":
        path = arguments.get("file_path", "")
        # 检测关键文件
        critical_patterns = [".env", "config", "database", ".db", "credentials", "secret"]
        if any(pattern in path.lower() for pattern in critical_patterns):
            return (ToolRiskLevel.HIGH, f"删除关键文件: {path}")
        return (ToolRiskLevel.HIGH, "删除文件操作")
    
    if tool_name in ["run_command", "execute_command", "exec_command"]:
        cmd = arguments.get("command", "")
        # 检测危险命令
        dangerous_patterns = [
            r"rm\s+-rf",           # 递归删除
            r"dd\s+if=",           # 磁盘操作
            r"mkfs",               # 格式化
            r">/dev/",             # 写入设备
            r"format",             # 格式化
            r"del\s+/s",           # Windows 递归删除
            r"shutdown",           # 关机
            r"reboot",             # 重启
            r"chmod\s+777",        # 危险权限
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, cmd.lower()):
                return (ToolRiskLevel.HIGH, f"危险命令: {cmd[:50]}")
        return (ToolRiskLevel.MEDIUM, "执行命令")

    # open_terminal 带非空 command 时，本质上同 run_command：静默执行任意命令并返回输出。
    # 必须套与 run_command 同样的危险命令检测。仅在 visible=True 且 command 为空时（仅弹终端）才走 MEDIUM。
    if tool_name == "open_terminal":
        cmd = arguments.get("command", "") or ""
        if cmd.strip():
            dangerous_patterns = [
                r"rm\s+-rf", r"dd\s+if=", r"mkfs", r">/dev/",
                r"format", r"del\s+/s", r"shutdown", r"reboot", r"chmod\s+777",
            ]
            for pattern in dangerous_patterns:
                if re.search(pattern, cmd.lower()):
                    return (ToolRiskLevel.HIGH, f"危险命令 (open_terminal): {cmd[:50]}")
            return (ToolRiskLevel.MEDIUM, "通过 open_terminal 执行命令")
        return (ToolRiskLevel.MEDIUM, "打开终端窗口")
    
    # 检测系统关键路径写入
    if tool_name in ["write_file", "write_to_file", "create_file", "edit_file", "search_and_replace"]:
        # search_and_replace 的目标路径可由 query/path 任一项给出；优先用 path
        path = arguments.get("file_path", arguments.get("path", ""))
        critical_paths = ["/etc/", "/sys/", "/proc/", "C:\\Windows\\", "C:\\Program Files\\"]
        if any(path.startswith(cp) for cp in critical_paths):
            return (ToolRiskLevel.HIGH, f"写入系统关键路径: {path}")

    # 3. 写入/修改操作 → MEDIUM
    write_tools = {
        "edit_file", "write_to_file", "replace_in_file",
        "search_and_replace",
        "create_skill", "create_directory", "move_file",
    }
    # open_terminal 已在上方单独分档处理，这里不再重复登记为 MEDIUM。
    if tool_name in write_tools:
        return (ToolRiskLevel.MEDIUM, "文件修改操作")
    
    # 4. 未知工具 → MEDIUM（保守策略）
    return (ToolRiskLevel.MEDIUM, "未分类工具，建议审查")


# 测试代码
if __name__ == "__main__":
    test_cases = [
        ("read_file", {"file_path": "test.txt"}),
        ("delete_file", {"file_path": ".env"}),
        ("delete_file", {"file_path": "temp.log"}),
        ("run_command", {"command": "rm -rf /"}),
        ("run_command", {"command": "ls -la"}),
        ("edit_file", {"file_path": "code.py", "content": "print('hello')"}),
        # 新增覆盖：search_file_with_name 只读应 SAFE
        ("search_file_with_name", {"file_name": "main.py"}),
        # search_and_replace 写操作应 MEDIUM（非关键路径）
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "./src.py"}),
        # search_and_replace 写入系统关键路径应 HIGH
        ("search_and_replace", {"query": "foo", "new_content": "bar", "path": "C:\\Windows\\System32\\x.cfg"}),
        # open_terminal 仅弹终端应 MEDIUM
        ("open_terminal", {"visible": True}),
        # open_terminal 带危险命令应 HIGH
        ("open_terminal", {"command": "rm -rf /", "visible": False}),
        # open_terminal 带普通命令应 MEDIUM
        ("open_terminal", {"command": "git status", "visible": False}),
    ]
    
    print("风险分级测试:")
    for tool_name, args in test_cases:
        level, reason = classify_tool_risk(tool_name, args)
        print(f"  {tool_name}: {level.upper()} - {reason}")
