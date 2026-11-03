import asyncio
import time
import uuid

_EXPIRE_SEC = 600  # 10 分钟没人消费就作废(流早死了,别让 POST 挂满 coroutine)

_injections: dict[str, dict] = {}
_lock = asyncio.Lock()


async def set_injection_target(session_id: str) -> None:
    """chat_stream 开始时调用:标记该会话的流可以接收注入。"""
    async with _lock:
        _injections[session_id] = {"stream_alive": True}


async def clear_injection_target(session_id: str) -> None:
    """chat_stream 结束时调用:标记槽死亡并唤醒还在等投递的 POST。"""
    async with _lock:
        slot = _injections.get(session_id)
        if slot is not None:
            slot["stream_alive"] = False
        _injections.pop(session_id, None)
    if slot and slot.get("event"):
        slot["event"].set()


async def submit_injection(session_id: str, text: str) -> dict:
    """POST /chat/inject:把消息放进该会话的注入槽,等流消费后返回。

    返回 {status, delivered} —— 流已结束/未启动时 status="no_stream",
    前端应退回「排队」路径而不是报错。
    """
    text = (text or "").strip()
    if not text:
        return {"status": "empty"}

    async with _lock:
        # 没有正在跑的流(或流还没跑到注册点):不排队,让前端走普通发送
        if session_id not in _injections:
            return {"status": "no_stream"}
        # 前一条还没被消费:拒绝叠加,前端提示「上一条还在送」
        if _injections[session_id].get("text"):
            return {"status": "busy"}
        slot = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "ts": time.time(),
            "event": asyncio.Event(),
            "stream_alive": True,
        }
        _injections[session_id] = slot

    # 等流来取(最多等 _EXPIRE_SEC,防 POST 永挂)
    try:
        await asyncio.wait_for(slot["event"].wait(), timeout=_EXPIRE_SEC)
    except asyncio.TimeoutError:
        # 超时:流大概已经死了,清槽避免影响下一次
        async with _lock:
            if _injections.get(session_id) is slot:
                _injections.pop(session_id, None)
        return {"status": "timeout"}
    # 醒来后鉴别死活:被 take 消费 = delivered;被 clear 杀死 = no_stream
    return (
        {"status": "delivered", "id": slot["id"]}
        if slot.get("stream_alive")
        else {"status": "no_stream"}
    )


async def take_injection(session_id: str) -> str | None:
    """流侧:取走一条待注入的 user 消息(无则立即返回 None)。

    在工具轮间隙调用;取到的文本由调用方拼进 running_msgs,
    模型下一轮就能看到用户的补充。
    """
    async with _lock:
        slot = _injections.get(session_id)
        if not slot or not slot.get("text"):
            return None
        # 过期保护:用户提交后流又跑了很久都没到轮间隙,别再塞进上下文
        if time.time() - slot.get("ts", 0) > _EXPIRE_SEC:
            _injections.pop(session_id, None)
            return None
        text = slot["text"]
        slot["text"] = ""  # 消费掉,槽保留给投递信号
    if slot.get("event"):
        slot["event"].set()
    return text


async def has_pending(session_id: str) -> bool:
    """诊断用:该会话是否有未消费的注入。"""
    async with _lock:
        return bool(_injections.get(session_id, {}).get("text"))
