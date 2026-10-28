from __future__ import annotations
import os
import subprocess
import sys
import threading

PACKAGE = "edge-tts"
_PIP_TIMEOUT = 180.0
# 多个请求同时 403 时,别让两个 pip 抢同一个环境
_upgrade_lock = threading.Lock()

def installed_version() -> str:
    """已安装的 edge-tts 版本;未安装或导入失败返回空串。"""
    try:
        import edge_tts
        return str(getattr(edge_tts, "__version__", "") or "")
    except Exception:
        return ""

def upgrade() -> tuple[bool, str]:
    """跑 `pip install -U edge-tts`。返回 (是否成功, 输出摘要)。

    同步阻塞,调用方应丢进线程池。失败不抛错,把原因塞进摘要里返回,
    让上层能把它拼进用户可见的错误提示。
    """
    # 打包版没有可用的 pip:sys.executable 是应用本体,`-m pip` 会把它再启动一遍
    # (等于多开一个后端,还会白白卡到 timeout)。直接拒绝并说清出路。
    if getattr(sys, "frozen", False):
        return False, "打包版不能自动升级 edge-tts(pip 不可用),需随 Symbix 新版本更新"
    cmd = [sys.executable, "-m", "pip", "install", "-U", PACKAGE, "--no-input", "--disable-pip-version-check"]
    try:
        with _upgrade_lock:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_PIP_TIMEOUT,
                env=dict(os.environ),
            )
    except subprocess.TimeoutExpired:
        return False, f"pip 超时(>{_PIP_TIMEOUT:.0f}s)"
    except Exception as e:
        # 打包环境里可能根本没有 pip,属于可预期失败
        return False, f"无法执行 pip: {e}"

    raw = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    tail = lines[-1] if lines else ""
    if proc.returncode != 0:
        return False, tail or f"pip 退出码 {proc.returncode}"
    # pip 成功时最后一行形如 "Successfully installed edge-tts-7.3.1"
    return True, tail or "已升级"

def reload_modules() -> None:
    """把 edge_tts 及其子模块从 sys.modules 清掉,让下次 import 拿到新代码。

    edge_tts 无跨调用全局状态(音色表每次现拉),重载是安全的。
    """
    for name in [m for m in list(sys.modules) if m == "edge_tts" or m.startswith("edge_tts.")]:
        sys.modules.pop(name, None)

def ensure_updated() -> tuple[bool, str]:
    """给「立即升级」按钮用:升级 + 清缓存。返回 (是否成功, 摘要)。"""
    ok, detail = upgrade()
    if ok:
        reload_modules()
    return ok, detail