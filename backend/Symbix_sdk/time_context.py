from __future__ import annotations
from datetime import datetime
_WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

def local_now() -> datetime:
    """当前本地时间(带时区信息)。"""
    return datetime.now().astimezone()


def current_time_line(now: datetime | None = None) -> str:
    n = now or local_now()
    tz = n.tzname() or ""
    stamp = f"{n:%Y-%m-%d} {_WEEKDAY_CN[n.weekday()]} {n:%H:%M}"
    return f"[当前时间] {stamp} ({tz})" if tz else f"[当前时间] {stamp}"