"""Python 代码执行工具。

为什么要有它,而不是让模型自己拼 ``open_terminal python xxx.py``:

- 模型写命令经常把引号/换行写坏(尤其多行脚本、中文路径);
- 直接 ``python script.py`` 用的是系统 Python,装包会污染用户环境;
- 走 ``uv run`` 能把依赖隔离,但模型不会主动加 PEP 723 头。

所以这里包一层:模型只给代码(和可选依赖列表),剩下的写入临时文件、
补依赖声明、选运行时、清理现场都由后端做。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from Symbix_sdk.tools.file_pipeline import assert_path_allowed

#: 执行超时上限(秒)。数据分析/绘图几分钟够用,再长应该走 open_terminal。
RUN_TIMEOUT_MAX = 900

#: 输出只保留尾部这么多字符:脚本可能打印几十 MB 表格/日志,
#: 全量塞进上下文会直接挤爆 budget,CJK 尤其危险。
OUTPUT_TAIL = 20_000


def _pick_runner() -> tuple[list[str], str]:
    """挑一个 Python 运行时,返回 (命令行前缀, 说明)。

    优先级:内置 uv(隔离环境,不污染系统) > 系统 python。
    uv 缺失时退回 python,并让调用方在提示里说明「会装进系统环境」。
    """
    try:
        from Symbix_sdk.runtime_env import detect_runtime

        cmds = detect_runtime()["commands"]
    except Exception:
        cmds = {}

    uv = cmds.get("uv")
    if uv:
        return [uv["path"], "run", "--no-project"], "uv"

    py = cmds.get("python") or {}
    exe = py.get("path") or shutil.which("python") or shutil.which("python3")
    if exe:
        return [exe], "python"
    return [], ""


def _build_script(code: str, deps: list[str], python_version: str) -> str:
    """给代码补上 PEP 723 内联依赖头(uv 据此自动建环境)。"""
    if not deps:
        return code
    quoted = ", ".join(f'"{d}"' for d in deps)
    header = ["# /// script"]
    if python_version:
        header.append(f'# requires-python = ">={python_version}"')
    header.append(f"# dependencies = [{quoted}]")
    header.append("# ///")
    return "\n".join(header) + "\n" + code


def run_python(
    code: str,
    dependencies: list[str] | None = None,
    timeout: int = 120,
    working_directory: str = "",
) -> str:
    """执行一段 Python 代码并返回输出。

    Args:
        code: 完整 Python 源码。
        dependencies: 需要额外安装的包名列表(如 ["pandas", "matplotlib"])。
        timeout: 超时秒数。
        working_directory: 工作目录;留空则用第一个工作区,再退到进程临时目录。

    Returns:
        形如 ``[runner=uv] [exit_code=0]\\n<stdout>`` 的文本。
    """
    code = (code or "").strip()
    if not code:
        return "[Error] code 为空"

    runner, runner_name = _pick_runner()
    if not runner:
        return "[Error] 找不到可用的 Python 运行时(既没有 uv 也没有 python)"

    try:
        timeout = int(timeout) if timeout is not None else 120
    except (TypeError, ValueError):
        timeout = 120
    timeout = max(1, min(timeout, RUN_TIMEOUT_MAX))

    deps = [str(d).strip() for d in (dependencies or []) if str(d).strip()]

    # ── 工作目录 ──
    cwd = (working_directory or "").strip()
    if not cwd:
        try:
            from Symbix_sdk.tools.file_pipeline import workspace_roots

            roots = workspace_roots()
            cwd = str(roots[0]) if roots else ""
        except Exception:
            cwd = ""
    if cwd:
        try:
            cwd = assert_path_allowed(cwd)
        except Exception as e:
            return f"[Error] working_directory 不允许: {e}"
        if not os.path.isdir(cwd):
            return f"[Error] working_directory 不存在: {cwd}"

    # ── 脚本落到临时目录,跑完必删 ──
    # 放临时目录而不是工作区:不污染用户项目,也避免被产物追踪误扫成"新产物"。
    tmp_dir = tempfile.mkdtemp(prefix="symbix_run_")
    script = Path(tmp_dir) / "script.py"
    try:
        # 只在 uv 下补 PEP 723 头;系统 python 不认这段注释头但也不报错,
        # 为了输出干净仍只在 uv 路径加。
        version = f"{sys.version_info.major}.{sys.version_info.minor}" if runner_name == "uv" else ""
        body = _build_script(code, deps, version)
        script.write_text(body, encoding="utf-8", newline="\n")

        cmd = runner + [str(script)]
        env = dict(os.environ)
        # uv 默认会把解析到的 Python 版本写进项目;--no-project 已经规避,
        # 这里再显式关掉进度条式的彩色输出,方便前端展示。
        env.setdefault("NO_COLOR", "1")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd or None,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"[Error] 执行超时(>{timeout}s)。长任务请改用 open_terminal 并显式给大 timeout。"
    except Exception as e:
        return f"[Error] 执行失败: {e}"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    parts = [f"[runner={runner_name}]"]
    if deps:
        parts.append(f"[deps={' '.join(deps)}]")
    if proc.stdout and proc.stdout.strip():
        parts.append(proc.stdout.rstrip())
    if proc.stderr and proc.stderr.strip():
        parts.append(f"[stderr]\n{proc.stderr.rstrip()}")
    parts.append(f"[exit_code={proc.returncode}]")

    out = "\n".join(parts)
    if len(out) > OUTPUT_TAIL:
        out = f"[已截断,只保留最后 {OUTPUT_TAIL} 字符]\n" + out[-OUTPUT_TAIL:]
    return out


PYTHON_TOOLS_SCHEMAS = {
    "run_python": {
        "risk_channel": "exec",
        "func": run_python,
        "description": (
            "执行一段 Python 代码并拿到输出。适合数据分析、计算、画图、批量处理文件、"
            "调用第三方库等 —— 比用 open_terminal 拼命令行更可靠(不用处理引号和路径转义)。"
            "依赖通过 dependencies 参数声明,会装到隔离环境,不污染用户的 Python。"
            "需要长期运行(几分钟以上)或要弹窗交互的任务请改用 open_terminal。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "完整的 Python 源码。多行直接用换行分隔,不要自己加 PEP 723 依赖头"
                        "(用 dependencies 参数即可)。print 的内容会作为结果返回。"
                    ),
                },
                "dependencies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "需要安装的第三方包,如 [\"pandas\", \"matplotlib\"];"
                        "标准库不需要填。首次安装会稍慢,之后有缓存。"
                    ),
                },
                "timeout": {
                    "type": "integer",
                    "description": f"超时秒数,默认 120,最大 {RUN_TIMEOUT_MAX}",
                },
                "working_directory": {
                    "type": "string",
                    "description": "工作目录;留空自动用当前工作区(脚本读写相对路径时用到)",
                },
            },
            "required": ["code"],
        },
    },
}
