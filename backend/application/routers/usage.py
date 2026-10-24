"""token 用量查询路由:/usage/summary。"""
from fastapi import APIRouter

from application.state import usage_store

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary")
def usage_summary(days: int = 30) -> dict:
    """日/周/月汇总 + 最近 days 天逐日明细(前端画柱状图用)。"""
    return usage_store.summary(days=min(max(days, 7), 90))


@router.get("/session")
def usage_session(session_id: str = "") -> dict:
    """会话级恢复数据:末轮完整 usage + 会话累计(前端切回会话时还原 usage 行)。"""
    if not session_id:
        return {"last": None, "total": {"prompt": 0, "output": 0, "total": 0, "calls": 0}}
    return usage_store.session_info(session_id)
