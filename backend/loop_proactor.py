"""强制使用 ProactorEventLoop 的 uvicorn loop factory。

背景:uvicorn 在 reload/subprocess 模式下,Windows 上会强制 SelectorEventLoop
(见 uvicorn/loops/asyncio.py: `if sys.platform == "win32" and not use_subprocess:
return asyncio.ProactorEventLoop; return asyncio.SelectorEventLoop`)。
SelectorEventLoop 不支持 asyncio.create_subprocess_exec,导致 STT(SenseVoice 子进程)
启动失败(503)。

方案:通过 `--loop loop_proactor:force_proactor` 传入自定义 loop factory。
uvicorn 0.36 的 asyncio_run 用 asyncio.Runner(loop_factory=...),Runner 会调用
loop_factory() 并把返回的实例当作 event loop —— 因此这里返回 ProactorEventLoop
实例即可,reload 模式下也能用 ProactorEventLoop,create_subprocess_exec 正常工作。
"""
from __future__ import annotations

import asyncio


def force_proactor() -> asyncio.AbstractEventLoop:
    """返回新的 ProactorEventLoop 实例(每次调用创建一个)。"""
    return asyncio.ProactorEventLoop()