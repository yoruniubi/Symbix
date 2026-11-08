import asyncio
import time
import uuid

# 用户补充最多等这么久被流消费。工具轮间隙通常是秒级，
# 等这么久还没被取走，说明这一轮插不进去了，让前端转「排队」，别让 POST 挂着。
_EXPIRE_SEC = 90


_injections: dict[str, dict] = {}
_lock = asyncio.Lock()


async def set_injection_target(session_id: str) -> None:
    """chat_stream 开始时调用:标记该会话的流可以接收注入。

    注意「流活着」不等于「插得进去」—— 只有工具轮之间才有消费点。
    真正的可插入性由 set_tool_loop_active 单独维护。
    """
    async with _lock:
        _injections[session_id] = {"stream_alive": True, "tool_loop": False}


async def set_tool_loop_active(session_id: str, active: bool) -> None:
    """标记该会话当前是否处在「工具轮循环」里(有轮间隙可以消费注入)。

    循环开始置 True、循环结束置 False。纯文本回复期间是 False ——
    这时候用户插话不可能被本轮吃进去,submit_injection 会立刻让它转排队,
    而不是让请求挂在那儿等到流结束(用户看到的是「按回车没反应」)。
    """
    async with _lock:
        slot = _injections.get(session_id)
        if slot is not None:
            slot["tool_loop"] = active


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

    返回 status:
    - delivered  流在轮间隙取走了,模型下一轮就能看到
    - no_stream  没有正在跑的流(或流还没跑到注册点)
    - queued     流在跑,但这一轮不会再有轮间隙(纯文本回复 / 收尾中),
                 或等太久没被消费 —— 前端应改成「本轮结束后自动发送」
    - busy       前一条补充还没被消费,拒绝叠加
    - empty      空文本
    """
    text = (text or "").strip()
    if not text:
        return {"status": "empty"}

    async with _lock:
        # 没有正在跑的流(或流还没跑到注册点):不排队,让前端走普通发送
        if session_id not in _injections:
            return {"status": "no_stream"}
        slot_now = _injections[session_id]
        # 前一条还没被消费:拒绝叠加,前端提示「上一条还在送」
        if slot_now.get("text"):
            return {"status": "busy"}
        # 当前不在工具轮循环里 → 本轮不可能有消费点,直接转排队,
        # 不占用槽、也不让请求挂住
        if not slot_now.get("tool_loop"):
            return {"status": "queued", "reason": "no_tool_round"}
        slot = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "ts": time.time(),
            "event": asyncio.Event(),
            "stream_alive": True,
            "tool_loop": True,
        }
        _injections[session_id] = slot

    # 等流来取(最多等 _EXPIRE_SEC,防 POST 永挂)
    try:
        await asyncio.wait_for(slot["event"].wait(), timeout=_EXPIRE_SEC)
    except asyncio.TimeoutError:
        # 超时:流大概卡住了,清槽并让前端排队,别丢用户这句话
        async with _lock:
            if _injections.get(session_id) is slot:
                _injections.pop(session_id, None)
        return {"status": "queued", "reason": "timeout"}
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
