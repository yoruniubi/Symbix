from __future__ import annotations
import asyncio

def force_proactor() -> asyncio.AbstractEventLoop:
    """返回新的 ProactorEventLoop 实例(每次调用创建一个)。"""
    return asyncio.ProactorEventLoop()