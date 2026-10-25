"""主动搭话(Proactive Companion)。

陪伴感的核心是「它想着我」:不只是被动应答,还会在合适的时机主动开口。
本模块挂在 main.py 的陪伴心跳(_companion_loop,每 60s)上,三类触发:

1. 空闲搭话 —— 距上次用户交互超过阈值,带随机抖动地冒一句(不机械)
2. 记忆回访 —— 从长期记忆里翻一条旧事,「还记得你说过 XX 吗」
3. 频控 —— 每日上限 + 最小间隔,弹幕总开关关闭时整体静默

事件通过 pet_action 总线发布,type=proactive,前端弹幕窗渲染成
可点击气泡;点击后经 Tauri 事件打开聊天窗并带入该条上下文。
"""
from __future__ import annotations

import random
import time
from typing import Any

from application.services.danmaku_service import danmaku_cfg, pick_danmaku
from application.services.pet_action import pet_action

# ── 配置(保守默认,不打扰优先)──────────────────────────
IDLE_THRESHOLD_S = 45 * 60          # 距上次交互超过 45 分钟才可能触发
MIN_GAP_S = 2 * 60 * 60             # 两条主动搭话至少间隔 2 小时
DAILY_LIMIT = 6                     # 每天最多 6 条
JITTER_S = 20 * 60                  # 触发判定加 0~20 分钟随机抖动
# 记忆回访只挑「有画面感」的类别:preference/constraint 这类事实型条目
# (「用户偏好小故事长度在 50 字左右」)念出来像系统日志,不像人话
RECALL_CATEGORIES = {"habit", "goal", "identity", "other"}
RECALL_PROBABILITY = 0.5            # 触发时 50% 概率走「记忆回访」,其余走普通搭话(伪随机)

# 触发性文案:以问句/邀请收尾,给用户一个「点它」的理由
_PROACTIVE_TEMPLATES: dict[str, list[str]] = {
    "idle": [
        "忙什么呢?休息一下,跟我说说话呗~",
        "突然想到你,最近还好吗?",
        "偷偷冒个泡~今天有什么开心的事吗?",
        "看你半天没动静,是遇到难题了吗?说出来我帮你想想~",
        "要不要过来聊两句?我给你留了位置~",
        "有点惦记你,冒个泡看看你在不在~",
    ],
    # 记忆回访的开场前缀,后接记忆内容摘要
    "recall": [
        "还记得吗,",
        "突然想起,",
        "想起来了,",
    ],
    "recall_tail": [
        "——最近怎么样,还惦记这事吗?",
        "——后来呢?我一直好奇后续~",
        "——现在有新进展吗?",
        "——要不要接着聊聊这个?",
    ],
}

# 运行期状态(进程内,无需持久化)
_state: dict[str, Any] = {
    "last_user_ts": time.time(),    # 启动时刻视为「刚交互过」,避免启动即搭话
    "last_emit_ts": 0.0,
    "today": "",
    "today_count": 0,
}


def note_user_interaction() -> None:
    """记录一次用户交互(聊天/语音等)。

    在消息入口(chat 路由)调用;主动搭话只在用户安静很久后才出现。
    """
    _state["last_user_ts"] = time.time()


def _daily_ok() -> bool:
    """每日限额检查:跨天清零,超出上限返回 False。"""
    import datetime as _dt
    today = _dt.date.today().isoformat()
    if _state["today"] != today:
        _state["today"] = today
        _state["today_count"] = 0
    return _state["today_count"] < DAILY_LIMIT


def _fetch_random_memory() -> dict | None:
    """从长期记忆随机摸一条适合回访的旧事;没有合适数据时返回 None。

    只取 RECALL_CATEGORIES 里的类别且长度足够 —— preference/constraint
    这类事实型条目念出来生硬,不适合直接对用户说。
    """
    try:
        from application.state import memory_store  # 延迟导入避免环
        hits = memory_store.get_active_memories()
        candidates = [
            h for h in hits
            if h.get("category") in RECALL_CATEGORIES
            and len(str(h.get("content", ""))) >= 12
        ]
        if not candidates:
            return None
        return random.choice(candidates)
    except Exception:
        return None


def _compose_recall_text(memory_hit: dict) -> str:
    """把一条记忆组装成回访文案(前缀 + 记忆摘要 + 尾问)。测试接口复用。"""
    content = str(memory_hit.get("content", "")).strip()
    if len(content) > 40:
        content = content[:37] + "…"
    return (random.choice(_PROACTIVE_TEMPLATES["recall"]) + content
            + random.choice(_PROACTIVE_TEMPLATES["recall_tail"]))


def _maybe_probe() -> dict[str, Any] | None:
    """心跳入口:判定此刻是否该主动搭话;该则发布事件并返回,否则 None。

    所有判定纯本地、零 LLM 成本;失败一律静默(陪伴功能不能反过来打扰排障)。
    """
    now = time.time()
    # 总开关/空闲开关关闭 → 整体静默(遵守用户对弹幕的意愿)
    if not danmaku_cfg.cfg.enabled or not danmaku_cfg.cfg.idle_enabled:
        return None
    # 频控:日限额 + 最小间隔
    if not _daily_ok() or now - _state["last_emit_ts"] < MIN_GAP_S:
        return None
    # 空闲判定 + 抖动:阈值基础上加随机量,避免「整 45 分钟必然冒泡」的机械感
    quiet_for = now - _state["last_user_ts"]
    if quiet_for < IDLE_THRESHOLD_S + random.uniform(0, JITTER_S):
        return None

    # 选择形态:记忆回访(概率性)或普通搭话
    ev: dict[str, Any]
    memory_hit = _fetch_random_memory() if random.random() < RECALL_PROBABILITY else None
    if memory_hit:
        text = _compose_recall_text(memory_hit)
        ev = {
            "type": "proactive",
            "text": text,
            "kind": "recall",
            "memory": memory_hit.get("content", ""),
            "ts": now,
        }
    else:
        text = pick_proactive("idle")
        if not text:
            return None
        ev = {"type": "proactive", "text": text, "kind": "idle", "ts": now}

    _state["last_emit_ts"] = now
    _state["today_count"] += 1
    # 复用 pet_action 总线:弹幕窗已订阅 /pet/events
    published = pet_action.publish(ev)
    return published or ev


def pick_proactive(kind: str) -> str:
    """从主动搭话文案池轮换抽取(与弹幕池同机制,避免连续重复)。"""
    templates = _PROACTIVE_TEMPLATES.get(kind) or []
    if not templates:
        return ""
    _pools: dict[str, list[str]] = getattr(pick_proactive, "_pools", {})
    _last: dict[str, str] = getattr(pick_proactive, "_last", {})
    pool = _pools.get(kind)
    if not pool:
        pool = list(templates)
        random.shuffle(pool)
        if len(pool) > 1 and pool[-1] == _last.get(kind):
            pool[-1], pool[0] = pool[0], pool[-1]
        _pools[kind] = pool
    text = pool.pop()
    _last[kind] = text
    pick_proactive._pools = _pools  # type: ignore[attr-defined]
    pick_proactive._last = _last  # type: ignore[attr-defined]
    return text
