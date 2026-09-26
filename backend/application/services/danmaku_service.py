"""弹幕文案服务。

桌宠陪伴感增强:在「任务完成 / 出错 / 空闲 / 时段问候」等时刻,
从本地模板库随机挑选一句俏皮话,通过 PetEventBus.publish 推送
给全屏弹幕窗口(与桌宠动作同一条 SSE 总线)。
"""
from __future__ import annotations
import os.path as osp
import random
from typing import Any
from Symbix_sdk.config.danmaku_config import DanmakuConfigManager
from application.services.pet_action import pet_action

# 弹幕配置单例(与 routers/danmaku.py 共用同一 json)
_DANMAKU_CONFIG_PATH = osp.join(
    osp.dirname(osp.abspath(__file__)),
    "..", "..", "Symbix_sdk", "config", "danmaku_config.json",
)
danmaku_cfg = DanmakuConfigManager(_DANMAKU_CONFIG_PATH)

# ── 模板库(本地零 LLM 成本)───────────────────────────────
# 每条模板可含 {reply_len} 占位(引用回复内容时用),目前先留空
_DANMAKU_TEMPLATES: dict[str, list[str]] = {
    # 任务完成
    "complete": [
        "搞定啦~🎉",
        "完成!下一件想做点什么?",
        "任务完成,夸夸我!",
        "搞定,收工~",
        "完成了,轻松拿捏~",
    ],
    # 出错
    "error": [
        "哎哟,卡了一下…",
        "这里出了点小问题,我调整一下~",
        "不好意思,我重新想想~",
    ],
    # 空闲(长时间没理我)
    "idle": [
        "在想发呆的时候,要找我哦~",
        "我在这儿等你呢~",
        "要不要聊聊天?",
        "你忙你的,我守着你~",
    ],
    # 早晨
    "morning": [
        "早安~新的一天也要元气满满!",
        "早上好,喝口水再开工~",
    ],
    # 下午
    "afternoon": [
        "下午好~要不要休息一下?",
        "太阳有点大,注意防晒哦~",
    ],
    # 晚上
    "evening": [
        "晚上好,今天辛苦啦~",
        "夜幕降临,适合说点悄悄话~",
    ],
    # 深夜
    "night": [
        "夜深了,早点休息~",
        "还在熬夜吗?要照顾好自己哦~",
    ],
}


def _hour_greeting(hour: int) -> str | None:
    """按本地时刻返回问候语;非问候时段返回 None。"""
    if 5 <= hour < 9:
        return random.choice(_DANMAKU_TEMPLATES["morning"])
    if 12 <= hour < 16:
        return random.choice(_DANMAKU_TEMPLATES["afternoon"])
    if 18 <= hour < 23:
        return random.choice(_DANMAKU_TEMPLATES["evening"])
    if 23 <= hour or hour < 4:
        return random.choice(_DANMAKU_TEMPLATES["night"])
    return None


def pick_danmaku(kind: str, *, hour: int | None = None) -> str:
    """按事件类型挑选一条弹幕文案。"""
    templates = _DANMAKU_TEMPLATES.get(kind)
    if not templates:
        return ""
    return random.choice(templates)


def emit_danmaku(kind: str, *, hour: int | None = None, extra: dict | None = None) -> dict[str, Any] | None:
    """发布一条弹幕事件(type=danmaku)到桌宠 SSE 总线。

    全屏弹幕窗口订阅 /pet/events,收到 type=danmaku 即飘字。
    返回推送的事件;文案为空(如未知 kind)或总开关关闭时返回 None。
    """
    if not danmaku_cfg.cfg.enabled:
        return None
    # 空闲/问候弹幕各自独立开关
    if kind == "idle" and not danmaku_cfg.cfg.idle_enabled:
        return None
    if kind in ("morning", "afternoon", "evening", "night") and not danmaku_cfg.cfg.greeting_enabled:
        return None
    text = pick_danmaku(kind, hour=hour)
    if not text:
        return None
    ev: dict[str, Any] = {
        "type": "danmaku",
        "text": text,
        "kind": kind,
        "ts": __import__("time").time(),
    }
    if extra:
        ev["extra"] = extra
    return pet_action.publish(ev)


def emit_idle_danmaku_if_quiet(*, min_interval_s: float | None = None, hour: int | None = None) -> dict | None:
    """空闲弹幕:距上次弹幕超过间隔才发,避免刷屏。

    间隔默认取配置 idle_interval_s,可覆盖。
    """
    import time as _time
    interval = min_interval_s or float(danmaku_cfg.cfg.idle_interval_s or 600)
    now = _time.time()
    last = getattr(emit_idle_danmaku_if_quiet, "_last_ts", 0.0)
    if now - last < interval:
        return None
    emit_idle_danmaku_if_quiet._last_ts = now
    return emit_danmaku("idle", hour=hour)