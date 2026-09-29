# 弹幕功能
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
from application.services.danmaku_service import danmaku_cfg
router = APIRouter(tags=["danmaku"])

@router.get("/danmaku/config")
async def get_danmaku_config():
    return {"config": danmaku_cfg.cfg.to_dict()}


class DanmakuConfigPatch(BaseModel):
    enabled: bool | None = None
    idle_enabled: bool | None = None
    greeting_enabled: bool | None = None
    idle_interval_s: int | None = None


@router.post("/danmaku/config")
async def update_danmaku_config(patch: DanmakuConfigPatch):
    danmaku_cfg.apply_patch(patch.model_dump(exclude_none=True))
    return {"status": "ok", "config": danmaku_cfg.cfg.to_dict()}


@router.post("/danmaku/config/reset")
async def reset_danmaku_config():
    danmaku_cfg.reset()
    return {"status": "ok", "config": danmaku_cfg.cfg.to_dict()}


@router.post("/danmaku/test")
async def test_danmaku():
    """触发一条测试弹幕(无视总开关,方便设置页试效果)。"""
    import random
    import time
    from application.services.danmaku_service import _DANMAKU_TEMPLATES
    from application.services.pet_action import pet_action
    text = random.choice(_DANMAKU_TEMPLATES["complete"])
    ev = {"type": "danmaku", "text": text, "kind": "complete", "ts": time.time()}
    pet_action.publish(ev)
    return {"status": "ok"}