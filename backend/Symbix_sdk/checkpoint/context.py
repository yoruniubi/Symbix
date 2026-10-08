from __future__ import annotations
from contextvars import ContextVar
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