"""Checkpoint 执行上下文 —— 通过 ContextVar 把当前 session/round 透传到工具函数。

- 工具函数（如 edit_file）签名由 LLM 工具 schema 决定，不能追加 session_id/round_id 参数；
  因此 chat.py 在 tool_registry.execute(...) 前 set_current(...)，工具内部 get_current() 读取。
- 读不到时（后台任务 / 非工具路径）安全降级：不记录文件 op。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_current_session: ContextVar[str] = ContextVar("chkpt_session", default="")
_current_round: ContextVar[str] = ContextVar("chkpt_round", default="")


def set_current(session_id: str, round_id: str) -> None:
    """进入工具执行作用域时调用。"""
    _current_session.set(session_id)
    _current_round.set(round_id)


def get_current() -> tuple[str, str]:
    """(session_id, round_id)；无上下文时返回空串。"""
    return _current_session.get(), _current_round.get()


def reset_current() -> None:
    _current_session.set("")
    _current_round.set("")