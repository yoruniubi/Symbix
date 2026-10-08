from __future__ import annotations
import os
import subprocess
import sys

from Symbix_sdk.tools.file_pipeline import assert_path_allowed

def open_terminal(
    command: str = "",
    shell: str = "powershell",
    working_directory: str = ".",
    timeout: int = 60,
    visible: bool = False,
) -> str:
    """在 PowerShell 或 CMD 中执行命令。

    Args:
        command: 要执行的命令；为空且 visible=True 时只打开终端窗口
        shell: 终端类型，'powershell' 或 'cmd'
        working_directory: 工作目录
        timeout: 后台模式超时（秒）
        visible: 是否弹出可见窗口
    """
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
    timeout = max(1, min(timeout, 300))

    if shell in ("powershell", "pwsh", "ps"):
        shell_exe = "powershell"
    elif shell in ("cmd", "command", "cmd.exe"):
        shell_exe = "cmd"
    else:
        return f"[Error] 不支持的 shell: {shell}。请使用 'powershell' 或 'cmd'。"

    cmd_str = (command or "").strip()

    # ---- 可见窗口模式 ----
    if visible:
        if sys.platform != "win32":
            return "[Info] visible 参数仅在 Windows 上生效。请在终端中手动执行命令。"

        if shell_exe == "powershell":
            if cmd_str:
                ps_cmd = (
                    f"Start-Process powershell -ArgumentList "
                    f"'-NoProfile -NoExit -Command \"cd '{cwd}'; "
                    + cmd_str.replace('"', '\\"')
                    + "; Write-Host \\\"`n--- 执行完毕，按任意键关闭窗口 ---\\\"; "
                    + "$null = $Host.UI.RawUI.ReadKey(\\\"NoEcho,IncludeKeyDown\\\")"
                    + "'"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return (
                    f"[Visible] 已在新的 PowerShell 窗口中执行命令。\n"
                    f"工作目录: {cwd}\n"
                    f"命令: {cmd_str}"
                )
            else:
                subprocess.run(
                    [
                        "powershell",
                        "Start-Process",
                        "powershell",
                        "-ArgumentList",
                        f"-NoProfile -NoExit -Command \"cd '{cwd}'; Write-Host 'Symbix Terminal — 已就绪'\"",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return (
                    f"[Visible] 已打开一个 PowerShell 窗口。\n"
                    f"工作目录: {cwd}"
                )
        else:
            # cmd
            if cmd_str:
                subprocess.run(
                    [
                        "cmd",
                        "/c",
                        "start",
                        '"Symbix Terminal"',
                        "cmd",
                        "/k",
                        f'cd /d "{cwd}" && {cmd_str}',
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return (
                    f"[Visible] 已在新的 CMD 窗口中执行命令。\n"
                    f"工作目录: {cwd}\n"
                    f"命令: {cmd_str}"
                )
            else:
                subprocess.run(
                    [
                        "cmd",
                        "/c",
                        "start",
                        '"Symbix Terminal"',
                        "cmd",
                        "/k",
                        f'cd /d "{cwd}"',
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                return (
                    f"[Visible] 已打开一个 CMD 窗口。\n"
                    f"工作目录: {cwd}"
                )

    # ---- 后台模式 ----
    if shell_exe == "powershell":
        shell_cmd = [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            cmd_str or 'Write-Host "（该命令无输出）"',
        ]
    else:
        shell_cmd = ["cmd", "/c", cmd_str or "echo （该命令无输出）"]

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
        return f"[Error] 命令超时（>{timeout}s）: {cmd_str}"
    except FileNotFoundError as e:
        return f"[Error] 找不到 shell 可执行文件: {e}"
    except Exception as e:
        return f"[Error] 执行失败: {e}"


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

TERMINAL_TOOLS_SCHEMAS = {
    "open_terminal": {
        "risk_channel": "exec",
        "func": open_terminal,
        "description": (
            "在 PowerShell 或 CMD 中执行命令。"
            "默认后台执行返回文本结果；设置 visible=True 可弹出独立终端窗口供用户查看/交互。"
            "当用户明确要求'打开终端'、'显示窗口'、'让我看看'时，应设置 visible=True。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要在终端中执行的命令。如果为空且 visible=True 则只打开终端窗口。",
                    "default": "",
                },
                "shell": {
                    "type": "string",
                    "enum": ["powershell", "cmd"],
                    "description": "终端类型：powershell 或 cmd。默认 powershell。",
                },
                "working_directory": {
                    "type": "string",
                    "description": "工作目录，默认为当前目录",
                },
                "timeout": {
                    "type": "integer",
                    "description": "命令超时时间（秒），仅后台模式有效，默认 60，最大 300",
                },
                "visible": {
                    "type": "boolean",
                    "description": (
                        "是否弹出可见的终端窗口。True=弹出独立窗口（用户可看到并交互），"
                        "False=后台静默执行并返回文本。当用户想看终端输出或交互时设为 True。"
                    ),
                    "default": False,
                },
            },
            "required": [],
        },
    },
}