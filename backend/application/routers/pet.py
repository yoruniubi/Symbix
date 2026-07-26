"""桌宠事件路由：SSE 订阅 + 手动触发（调试/外部调用）。"""
from __future__ import annotations

import asyncio
import json as _json

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.memory_ops import format_sse
from application.pet_bus import LOOP_ACTIONS, normalize_pet_action, pet_bus

router = APIRouter(tags=["pet"])


class PetActionRequest(BaseModel):
    action: str = Field(..., description="动作名，如 waving / jumping / happy")
    bubble: str = Field("", description="可选气泡文案")
    source: str = Field("api", description="来源标记")


@router.get("/pet/status")
async def pet_status():
    """当前桌宠状态快照。"""
    return {
        "status": "ok",
        "last_action": pet_bus.last_action,
        "recent": pet_bus.recent(5),
        "loop_actions": sorted(LOOP_ACTIONS),
    }


@router.post("/pet/action")
async def pet_action(req: PetActionRequest):
    """手动触发桌宠动作（调试或非 tool 调用）。"""
    action = (req.action or "").strip()
    if not action:
        raise HTTPException(status_code=400, detail="action 不能为空")
    event = pet_bus.emit(
        action,
        bubble=req.bubble or "",
        source=req.source or "api",
    )
    return {
        "status": "ok",
        "event": event,
        "normalized": event.get("action"),
    }


@router.get("/pet/events")
async def pet_events(
    request: Request,
    replay: int = Query(0, ge=0, le=8, description="连接时回放最近 N 条事件"),
):
    """Home 窗口订阅桌宠动作的 SSE 流。

    事件格式与聊天 SSE 一致：
      event: pet_action
      data: {"type":"pet_action","action":"waving",...}

    另有 heartbeat（约 20s）保持连接。
    """

    async def event_gen():
        queue = pet_bus.subscribe()
        try:
            # 连接问候
            yield format_sse(
                {
                    "type": "pet_hello",
                    "last_action": pet_bus.last_action,
                    "message": "pet events connected",
                }
            )
            # 可选回放
            if replay > 0:
                for ev in pet_bus.recent(replay):
                    yield format_sse(ev)

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield format_sse(event)
                except asyncio.TimeoutError:
                    # 心跳，避免代理/浏览器掐断空闲连接
                    yield format_sse(
                        {
                            "type": "pet_heartbeat",
                            "last_action": pet_bus.last_action,
                            "ts": __import__("time").time(),
                        }
                    )
        finally:
            pet_bus.unsubscribe(queue)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
