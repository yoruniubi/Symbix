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


@router.post("/companion/proactive/test")
async def test_proactive():
    """触发一条测试主动搭话(无视频控/空闲判定,方便设置页试效果)。

    与真实触发同一事件通道(type=proactive):弹幕窗会渲染成可点击气泡,
    可顺带验证「点击 → 开聊天窗」整条链路。
    """
    import time
    from application.services import companion_proactive as cp
    from application.services.pet_action import pet_action
    # 50% 概率带记忆回访,让两种形态都能试到;无可用记忆则自动退回普通搭话
    memory_hit = cp._fetch_random_memory()
    if memory_hit is None or __import__("random").random() < 0.5:
        text = cp.pick_proactive("idle")
        ev = {"type": "proactive", "text": text, "kind": "idle", "ts": time.time()}
    else:
        text = cp._compose_recall_text(memory_hit)
        ev = {
            "type": "proactive",
            "text": text,
            "kind": "recall",
            "memory": memory_hit.get("content", ""),
            "ts": time.time(),
        }
    pet_action.publish(ev)
    return {"status": "ok", "kind": ev["kind"], "text": text}


class ProactiveSeedBody(BaseModel):
    """主动搭话种子入会话的请求体。"""
    session_id: str
    text: str


@router.post("/companion/proactive/seed")
async def seed_proactive_message(body: ProactiveSeedBody):
    """把主动搭话内容写进后端会话记忆(assistant 角色)。

    聊天窗点击弹幕气泡后调用:搭话是「它先说的话」,需要进模型的历史,
    否则用户接话时模型不知道上下文(前端气泡只存 localStorage,不回传)。
    幂等:同会话同内容不重复写(Home 对 seed 有 3 次重试)。
    """
    from application.state import memory
    text = (body.text or "").strip()
    if not text or not body.session_id:
        return {"status": "skipped"}
    recent = memory.get_history(body.session_id, limit=6)
    if any(r.get("role") == "assistant" and r.get("content") == text for r in recent):
        return {"status": "ok", "dedup": True}
    memory.add(body.session_id, "assistant", text)
    return {"status": "ok"}