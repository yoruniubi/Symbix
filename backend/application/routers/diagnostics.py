"""前端内存哨兵的收数端。

WebView2 的 renderer 会随运行时长把私有内存涨到多个 GB(实测两个 renderer
各 6.3 GB,pagefile 被迫扩张)。Electron/Chromium 侧没有可用的开关能硬性限制
JS heap,所以只能前端自己采样 + 超阈值自救。

这里只做一件事:把前端报上来的采样写进日志,便于事后看增长曲线定位是哪个窗口。
"""

import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])

# 同一个窗口 5 分钟内只留一行,避免刷屏把日志撑爆(本身也是在防磁盘）
_REPORT_INTERVAL_SEC = 300.0
_last_report: dict[str, float] = {}


class ClientMemory(BaseModel):
    """前端一次采样。"""

    window: str = ""
    heap_mb: float = 0.0
    nodes: int = 0
    messages: int = 0
    uptime_min: float = 0.0


@router.post("/client-memory")
def client_memory(payload: ClientMemory) -> dict:
    """收一条前端内存采样,写进日志。返回是否真的记录了(便于前端调试)。"""
    key = payload.window or "unknown"
    now = time.time()
    last = _last_report.get(key, 0.0)
    if now - last < _REPORT_INTERVAL_SEC:
        return {"logged": False}
    _last_report[key] = now
    print(
        f"[mem] window={key} heap={payload.heap_mb:.0f}MB "
        f"nodes={payload.nodes} messages={payload.messages} "
        f"uptime={payload.uptime_min:.0f}min",
        flush=True,
    )
    return {"logged": True}
