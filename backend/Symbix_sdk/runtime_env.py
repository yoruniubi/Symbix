"""运行环境探测与兜底选择。

背景:

打包时为了「用户没装 node / python 也能跑 MCP」捆绑了 bun.exe 与 uv.exe
(约 128MB)。但如果只是把它们放进 PATH,Agent 基本用不到 ——

1. 捆绑的只有 ``uv`` / ``bun``,没有 ``uvx`` / ``bunx``,而模型最习惯写
   ``uvx`` / ``npx`` / ``bunx``,裸执行直接 "找不到命令";
2. 模型完全不知道这些运行时的存在,默认走系统 python + pip。

所以这里做两件事:

- ``detect_runtime()``:探测用户机器上有什么(系统优先),缺什么用内置兜底;
- ``ensure_shims()``:只为「系统缺失」的命令生成 ``.cmd`` 转发脚本,让
  ``uvx`` / ``bunx`` / ``npx`` 这些名字真的能敲。

原则是**系统优先**:用户已装 node/python/uv 就绝不覆盖他的,内置只做兜底。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

#: 探测结果缓存(仅进程内;环境在运行期变化极少,避免每条消息重复探测)
_detect_cache: dict | None = None

#: 一次 ``<cmd> --version`` 的等待上限。uv/bun 正常 100ms 内返回。
_VERSION_TIMEOUT = 8.0

#: 探测的运行时清单。``probe`` 是拿来判存在性的命令名,
#: ``version_arg`` 是取版本用的参数(取不到就留空,不影响判断存在)。
_PROBES: tuple[tuple[str, str], ...] = (
    ("python", "--version"),
    ("pip", "--version"),
    ("node", "--version"),
    ("npm", "--version"),
    ("npx", "--version"),
    ("uv", "--version"),
    ("uvx", "--version"),
    ("bun", "--version"),
    ("bunx", "--version"),
)

#: 内置可执行文件在 SDK 目录下的名字(不带扩展名),由 resource_path 补后缀。
_BUNDLED: dict[str, str] = {
    "uv": "Symbix_sdk/uv",
    "bun": "Symbix_sdk/bun",
}

#: shim 需要生成的名字 → (内置可执行, 前缀参数)
#: 只在「系统没有对应命令」时生成,绝不遮蔽用户已装的东西。
#: 实测 bun x 认识 npx 的 -y/--yes,不需要过滤参数,直接 %* 透传。
_SHIM_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    # uvx ≈ uv tool run
    "uvx": ("uv", ("tool", "run")),
    # bunx ≈ bun x;npx 也走 bun x(语义等价,-y 不冲突)
    "bunx": ("bun", ("x",)),
    "npx": ("bun", ("x",)),
}

SHIM_DIR_NAME = "_runtime_shims"


def _shim_dir() -> Path:
    """shim 目录:``<data>/_runtime_shims``。

    放 data 目录而不是 SDK 资源目录 —— 它是运行期生成的派生文件,
    不该进 git、不该进打包产物,清掉也不影响功能。
    """
    from .app_paths import data_root

    return data_root() / SHIM_DIR_NAME


def _bundled_exe(name: str) -> Path | None:
    """内置可执行文件路径(不存在则 None)。"""
    rel = _BUNDLED.get(name)
    if not rel:
        return None
    try:
        from .resource_path import sdk_binary

        p = sdk_binary(rel)
    except Exception:
        return None
    return p if p.is_file() else None


def _read_version(cmd: str, arg: str) -> str:
    """取版本号,失败返回空串(不影响「存在性」判断)。"""
    import re

    try:
        proc = subprocess.run(
            [cmd, arg],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_VERSION_TIMEOUT,
        )
        out = (proc.stdout or "") or (proc.stderr or "")
        line = out.strip().splitlines()[0] if out.strip() else ""
        # 第一个形如 1 / 1.2 / 1.2.3 的片段就是版本号:
        # "Python 3.12.7" / "v24.19.0" / "pip 25.2 from ... (python 3.10)" /
        # "uv 0.12.15 (d35f1f270 2026-09-15 ...)" 都能正确命中。
        m = re.search(r"\d+(?:\.\d+)+", line)
        return m.group(0) if m else ""
    except Exception:
        return ""


def _probe_system() -> dict[str, dict]:
    """探测系统 PATH 上真实存在的命令(**已排除内置目录**)。"""
    from .resource_path import resource_root

    bundled_dir = ""
    try:
        bundled_dir = str(resource_root()).lower()
    except Exception:
        pass

    found: dict[str, dict] = {}
    for name, version_arg in _PROBES:
        path = shutil.which(name)
        if not path:
            continue
        # which 可能命中我们注入进 PATH 的内置目录,那不是"系统自带"
        if bundled_dir and bundled_dir in os.path.dirname(path).lower():
            continue
        if os.path.dirname(path).lower().endswith(SHIM_DIR_NAME):
            continue
        found[name] = {
            "path": path,
            "version": _read_version(path, version_arg),
            "source": "system",
        }
    return found


def detect_runtime(refresh: bool = False) -> dict:
    """探测运行环境:系统优先,内置兜底。

    Args:
        refresh: 为 True 时丢弃缓存重新探测。

    Returns:
        ``{"commands": {名字: {"path", "version", "source"}}, "shim_dir": str}``
        ``source`` 取值 ``system`` / ``bundled``;内置项 ``path`` 指向
        SDK 里的 uv.exe / bun.exe。
    """
    global _detect_cache
    if _detect_cache is not None and not refresh:
        return _detect_cache

    commands = _probe_system()

    # 内置兜底:只补系统缺失的
    for name in _BUNDLED:
        if name in commands:
            continue
        exe = _bundled_exe(name)
        if exe:
            commands[name] = {
                "path": str(exe),
                "version": _read_version(str(exe), "--version"),
                "source": "bundled",
            }

    result = {"commands": commands, "shim_dir": str(_shim_dir())}
    _detect_cache = result
    return result


def _shim_body(exe: Path, prefix: tuple[str, ...]) -> str:
    """生成 ``.cmd`` 转发脚本的内容。

    只做一件事:把裸命令名转发到内置 exe,其余参数用 ``%*`` 原样透传
    —— 不解析引号,由 exe 自己处理,避免 PowerShell/cmd 转义差异出错。
    """
    return f'@echo off\r\n"{exe}" {" ".join(prefix)} %*\r\n'


def ensure_shims() -> list[str]:
    """为系统缺失的命令生成转发脚本,返回生成的命令名列表。

    幂等:每次启动重写(代价极小),但**系统已装的命令一律不生成** ——
    绝不能遮蔽用户自己的 npx / uvx。
    """
    if sys.platform != "win32":
        # 非 Windows 上 uv/bun 会以裸名存在,且用户一般有 uvx/bunx;
        # 需要时可用 `uv tool run` / `bun x`,不额外造脚本。
        return []

    detected = detect_runtime()
    commands = detected["commands"]
    shim_dir = Path(detected["shim_dir"])
    try:
        shim_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[runtime] shim 目录创建失败 {shim_dir}: {e}")
        return []

    created: list[str] = []
    for name, (bin_name, prefix) in _SHIM_SPECS.items():
        if name in commands:
            # 系统(npm 自带 npx / 用户装了 uvx)优先,不遮蔽
            continue
        exe = _bundled_exe(bin_name)
        if not exe:
            continue
        target = shim_dir / f"{name}.cmd"
        try:
            # 二进制写,避免文本模式把 \r\n 再翻一次
            target.write_bytes(_shim_body(exe, prefix).encode("ascii", errors="replace"))
            created.append(name)
        except OSError as e:
            print(f"[runtime] 写 shim 失败 {target}: {e}")
    return created


def runtime_path_entries() -> list[str]:
    """要加进 PATH 的目录(内置运行时目录 + shim 目录),系统优先排序。

    注意顺序:**shim 目录在前**,内置目录在后 —— shim 只会转发系统缺失的
    命令,放在前面不会遮蔽用户已装的东西;而内置目录放最后,确保系统
    自带的 node/python 永远优先于捆绑运行时。
    """
    entries: list[str] = []
    try:
        shim = str(_shim_dir())
        if os.path.isdir(shim):
            entries.append(shim)
    except Exception:
        pass
    for name in _BUNDLED:
        exe = _bundled_exe(name)
        if exe:
            d = str(exe.parent)
            if d not in entries:
                entries.append(d)
    return entries


def describe_runtime() -> str:
    """给 system prompt 用的一段纯文本环境说明。"""
    detected = detect_runtime()
    commands = detected["commands"]
    if not commands:
        return ""

    def fmt(name: str) -> str:
        info = commands.get(name)
        if not info:
            return ""
        ver = f" {info['version']}" if info["version"] else ""
        src = "内置" if info["source"] == "bundled" else "系统"
        return f"{name}{ver}({src})"

    items = [s for s in (fmt(n) for n, _ in _PROBES) if s]
    if not items:
        return ""

    has_py = "python" in commands
    has_uv = "uv" in commands
    has_node = "node" in commands
    has_js = has_node or "bun" in commands

    lines = [
        "[运行环境]",
        "本机可用运行时:" + "、".join(items),
    ]
    if has_uv:
        lines.append(
            "- 跑 Python 代码优先用 `uv run <脚本路径>`:它会自动准备隔离环境,"
            "不污染系统 Python。脚本开头可写 PEP 723 内联依赖声明"
            "(# /// script / # dependencies = [\"包名\"] / # ///),uv 会自动装好。"
            "没有内联声明时也可以 `uv run --with 包名 <脚本>`。"
        )
        lines.append("- 装 Python 库用 `uv add`(项目内)或 `uv pip install`;**不要**直接 `pip install` 到系统环境。")
    elif has_py:
        lines.append("- 跑 Python 代码用 `python <脚本路径>`;装库用 `pip install`,并注意会写进系统环境。")
    if has_js:
        lines.append(
            "- 跑 Node/JS 脚本优先 `npx` / `node`;一次性用包命令时 `bunx` 与 `npx` 等价。"
        )
    lines.append("- 上面标「内置」的是 Symbix 自带的运行时,不占用用户环境;标「系统」的是用户自己装的那份。")
    return "\n".join(lines)
