"""桌宠动作事件总线。

native 工具 emit_pet_action 把动作写入总线；
Home 窗口通过 GET /pet/events (SSE) 订阅并播放动画。
支持同步线程 emit + 异步 SSE 消费者。
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections import deque
from typing import Any


# 与前端 Home.vue ROWS 对齐的规范动作
PET_ACTIONS = frozenset(
    {
        "idle",
        "waving",
        "jumping",
        "failed",
        "waiting",
        "review",
        "running",
        "runningRight",
        "runningLeft",
        # 语义别名（emit 时会归一化）
        "happy",
        "thinking",
        "sad",
        "error",
        "celebrate",
        "wave",
        "jump",
    }
)

# 语义别名 → 实际 spritesheet 状态
ACTION_ALIASES: dict[str, str] = {
    "happy": "jumping",
    "celebrate": "jumping",
    "jump": "jumping",
    "wave": "waving",
    "thinking": "review",
    "sad": "failed",
    "error": "failed",
}

# 可循环播放的状态（与前端 LOOP_STATES 一致）
LOOP_ACTIONS = frozenset(
    {"idle", "waiting", "running", "runningRight", "runningLeft"}
)


def normalize_pet_action(action: str) -> str:
    raw = (action or "").strip()
    if not raw:
        return "idle"
    key = raw
    # 容错：大小写、连字符
    lowered = raw.replace("-", "").replace("_", "").lower()
    lookup = {
        "idle": "idle",
        "waving": "waving",
        "wave": "waving",
        "jumping": "jumping",
        "jump": "jumping",
        "failed": "failed",
        "waiting": "waiting",
        "review": "review",
        "running": "running",
        "runningright": "runningRight",
        "runningleft": "runningLeft",
        "happy": "happy",
        "celebrate": "celebrate",
        "thinking": "thinking",
        "sad": "sad",
        "error": "error",
    }
    key = lookup.get(lowered, raw)
    return ACTION_ALIASES.get(key, key)


class PetEventBus:
    """线程安全的桌宠事件总线。"""

    def __init__(self, history_size: int = 8):
        self._lock = threading.Lock()
        self._subscribers: list[asyncio.Queue] = []
        self._history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self._last_action: str = "idle"

    @property
    def last_action(self) -> str:
        return self._last_action

    def emit(
        self,
        action: str,
        *,
        bubble: str = "",
        source: str = "tool",
        session_id: str = "",
        extra: dict | None = None,
    ) -> dict[str, Any]:
        """同步发布桌宠动作。可从工具线程 / 任意线程调用。"""
        normalized = normalize_pet_action(action)
        event: dict[str, Any] = {
            "type": "pet_action",
            "id": uuid.uuid4().hex[:12],
            "action": normalized,
            "raw_action": action,
            "bubble": (bubble or "").strip()[:120],
            "loop": normalized in LOOP_ACTIONS,
            "source": source,
            "session_id": session_id or "",
            "ts": time.time(),
        }
        if extra:
            event["extra"] = extra

        with self._lock:
            self._last_action = normalized
            self._history.append(event)
            queues = list(self._subscribers)

        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # 丢最旧，再塞一次，避免卡死
                try:
                    _ = q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(event)
                except Exception:
                    pass
            except Exception:
                pass

        return event

    def subscribe(self, maxsize: int = 32) -> asyncio.Queue:
        """注册一个异步订阅队列（供 SSE 使用）。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def recent(self, n: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._history)
        return items[-n:] if n > 0 else items


# 进程级单例
pet_bus = PetEventBus()
