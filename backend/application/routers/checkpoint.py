from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from application.services.line_diff import build_line_diff
from application.state import checkpoint_recorder
from Symbix_sdk.tools.file_pipeline import assert_path_allowed

router = APIRouter(tags=["checkpoint"])


class PruneRequest(BaseModel):
    keep_recent_rounds: int = 50


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


@router.post("/sessions/{session_id}/timeline/prune")
async def session_timeline_prune(session_id: str, req: PruneRequest):
    """清理旧 round：保留最近 N 个 round，删掉其余记录，并顺带回收孤儿 blob。"""
    if req.keep_recent_rounds < 1:
        raise HTTPException(status_code=422, detail="keep_recent_rounds 至少为 1")
    result = checkpoint_recorder.prune(session_id, keep_recent_rounds=req.keep_recent_rounds)
    return {"session_id": session_id, **result}


@router.get("/sessions/{session_id}/checkpoint/file-op/{record_id}/diff")
async def file_op_diff(session_id: str, record_id: str):
    """回溯读：按 record_id 取某条 file_op 的 before/after 内容。"""
    rec = checkpoint_recorder.store.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    if rec.get("kind") != "file_op":
        raise HTTPException(status_code=400, detail="record is not a file_op")
    payload = rec.get("payload") or {}
    path = payload.get("path", "")
    blob_stored = bool(payload.get("blob_stored"))

    if not blob_stored:
        return {
            "record_id": record_id,
            "session_id": session_id,
            "path": path,
            "content_before": None,
            "content_after": None,
            "size_before": payload.get("size_before"),
            "size_after": payload.get("size_after"),
            "diff": None,
            "note": "该文件未存储可回退内容(可能是二进制文件或超出大小限制)",
        }

    content_before = None
    content_after = None
    if payload.get("hash_before"):
        content_before = checkpoint_recorder.get_blob(payload["hash_before"])
    if payload.get("hash_after"):
        content_after = checkpoint_recorder.get_blob(payload["hash_after"])

    return {
        "record_id": record_id,
        "session_id": session_id,
        "path": path,
        "content_before": content_before,
        "content_after": content_after,
        "size_before": payload.get("size_before"),
        "size_after": payload.get("size_after"),
        "size_delta": payload.get("size_delta"),
        "op": payload.get("op"),
        "blob_stored": True,
        # git 风格行级 diff,前端按增删着色(新增绿 / 删除红)
        "diff": build_line_diff(content_before, content_after),
    }


@router.post("/sessions/{session_id}/checkpoint/file-op/{record_id}/restore")
async def file_op_restore(session_id: str, record_id: str):
    """回溯写 / 撤销新建。

    - edit/delete 场景:用 hash_before 内容回写覆盖 path(delete 则重建文件)
    - create 场景(无 hash_before):回溯语义 = 删除该文件(撤销新建),
      与「AI 创建了错误的文件想撤回」的操作意图一致

    高风险操作:沙箱校验 + 恢复动作本身也 emit 一条 file_op 保持审计链。
    """
    import os
    import shutil

    rec = checkpoint_recorder.store.get_record(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="record not found")
    if rec.get("kind") != "file_op":
        raise HTTPException(status_code=400, detail="record is not a file_op")
    payload = rec.get("payload") or {}
    if rec.get("session_id") != session_id:
        raise HTTPException(status_code=400, detail="record 不属于该 session")

    op = payload.get("op", "")
    path = payload.get("path", "")
    has_before = bool(payload.get("blob_stored") and payload.get("hash_before"))

    # 沙箱校验:不允许恢复到沙箱外路径
    try:
        path = assert_path_allowed(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"路径校验失败: {e}")

    # —— create 场景:无 before 快照,回溯 = 删除新建的文件
    if op == "create" and not has_before:
        if os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"撤销新建失败: {e}")
        # 撤销动作本身 emit 一条 file_op(op="uncreate") 保持审计链;
        # 保留 hash_before 指向被删内容,让用户仍可查看 / 二次恢复
        checkpoint_recorder.emit_file_op(
            session_id=session_id,
            round_id=rec.get("round_id", "restore"),
            op="uncreate",
            path=path,
            size_before=payload.get("size_after"),
            size_after=0,
            hash_before=payload.get("hash_after"),
            hash_after=None,
            blob_stored=True,
        )
        return {
            "record_id": record_id,
            "session_id": session_id,
            "path": path,
            "restored": True,
            "action": "uncreate",
            "size_after": 0,
        }

    # —— 其余场景必须有 before 快照才能回退
    if not has_before:
        raise HTTPException(
            status_code=400,
            detail="该记录未存储可回退内容(二进制/超限文件无法恢复)",
        )

    content_before = checkpoint_recorder.get_blob(payload["hash_before"])
    if content_before is None:
        raise HTTPException(status_code=404, detail="before blob not found")

    # 当前文件内容(如果存在)作为 after 快照
    cur_content = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cur_content = f.read()
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError, PermissionError):
        pass

    # 写入恢复内容
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content_before)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复写入失败: {e}")

    # 恢复动作本身也要 emit 一条 file_op(op="restore") 保持审计链
    hash_cur = checkpoint_recorder.put_blob(cur_content) if cur_content else None
    hash_restored = checkpoint_recorder.put_blob(content_before)
    checkpoint_recorder.emit_file_op(
        session_id=session_id,
        round_id=rec.get("round_id", "restore"),
        op="restore",
        path=path,
        size_before=len(cur_content) if cur_content is not None else None,
        size_after=len(content_before),
        hash_before=hash_cur,
        hash_after=hash_restored,
        blob_stored=True,
    )

    return {
        "record_id": record_id,
        "session_id": session_id,
        "path": path,
        "restored": True,
        "action": "restore",
        "hash_after": hash_restored,
        "size_after": len(content_before),
    }
