"""Agent 行为 Checkpoint 查询接口。

提供给前端时间线视图（Checkpoints 侧栏面板）：
- GET /sessions/{sid}/timeline         整 session 的事件流（按 seq 升序）
- GET /sessions/{sid}/timeline/rounds  只取 round 总结（前端折叠头部用）
- GET /sessions/{sid}/timeline/summary 头部 overview（统计计数）

写 checkpoint 不在这里——写是 chat 路由在工具执行 / round 闭合时 fire-and-forget
通过 application.state.checkpoint_recorder 的 emit_* 接口完成的，这里只负责读。
"""
from fastapi import APIRouter, HTTPException, Query

from application.state import checkpoint_recorder

router = APIRouter(tags=["checkpoint"])


@router.get("/sessions/{session_id}/timeline")
async def session_timeline(
    session_id: str,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
):
    """某一 session 的所有行为事件。按 seq 升序、可分页。"""
    rows = checkpoint_recorder.timeline(session_id, limit=limit, offset=offset)
    return {"session_id": session_id, "count": len(rows), "records": rows}


@router.get("/sessions/{session_id}/timeline/summary")
async def session_timeline_summary(session_id: str):
    """头部统计：各类事件计数 + 错误总数 + 时间范围。"""
    s = checkpoint_recorder.summary(session_id)
    return {"session_id": session_id, **s}


@router.get("/sessions/{session_id}/timeline/rounds")
async def session_timeline_rounds(session_id: str):
    """所有 round 总结点（kind="round"），前端用以快速列出每轮 user→agent 摘要。

    不直接在 recorder 里做 SQL 过滤、用 timeline 后在 Python 里 filter——
    一个 session 通常 round 不多、避免再开一个 SQL 接口。
    """
    rows = checkpoint_recorder.timeline(session_id, limit=2000, offset=0)
    rounds = [r for r in rows if r.get("kind") == "round"]
    return {"session_id": session_id, "count": len(rounds), "rounds": rounds}


@router.get("/sessions/{session_id}/timeline/rounds/{round_id}")
async def session_timeline_round_detail(session_id: str, round_id: str):
    """某一 round 内的所有事件（工具调用 + round 总结点自己）。按 seq 升序。"""
    rows = checkpoint_recorder.store.list_by_round(session_id, round_id)
    return {"session_id": session_id, "round_id": round_id, "count": len(rows), "records": rows}
