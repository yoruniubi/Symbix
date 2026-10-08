from __future__ import annotations
import os
import uuid
from typing import Optional

from .schema import (
    CheckpointRecord,
    RecordKind,
    ToolCallRecord,
    FileOpRecord,
    CommandRecord,
    McpCallRecord,
    RoundRecord,
)
from .store import CheckpointStore
from .blob_store import BlobStore


class CheckpointRecorder:
    """单例 recorder。不要直接 new，用 `get_recorder()`。"""

    def __init__(self, store: CheckpointStore, blob_store: Optional[BlobStore] = None):
        self.store = store
        self.blob_store = blob_store or BlobStore(
            os.path.join(os.path.dirname(os.path.abspath(store.db_path)), "checkpoint_blobs")
        )

    # ── 内部工具 ──────────────────────────────────────────────────
    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    def _emit(self, rec: CheckpointRecord) -> None:
        """写入 + 容错：失败不抛、不阻断主流程。"""
        try:
            self.store.insert(rec)
        except Exception as e:  # pragma: no cover - 写 checkpoint 失败不能影响业务
            print(f"[checkpoint] insert failed (kind={rec.kind}, session={rec.session_id}): {e}")

    # ── 对外 emit_* 接口 ───────────────────────────────────────────
    def emit_tool_call(
        self,
        *,
        session_id: str,
        round_id: str,
        tool_name: str,
        arguments: dict,
        risk_level: str = "unknown",
        approved: bool = True,
        status: str = "ok",
        error: Optional[str] = None,
        result_snippet: str = "",
        result_truncated: bool = False,
    ) -> str:
        """记一条 native/skill 工具调用。"""
        rec = CheckpointRecord(
            id=self._new_id(),
            kind=RecordKind.TOOL_CALL,
            session_id=session_id,
            round_id=round_id,
            seq=0,                       # store 会填充
            status=status,
            error=error,
            payload=ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments or {},
                risk_level=risk_level,
                approved=approved,
                result_snippet=result_snippet[:500],
                result_truncated=result_truncated or len(result_snippet) > 500,
            ).model_dump(mode="json"),
        )
        self._emit(rec)
        return rec.id

    def emit_file_op(
        self,
        *,
        session_id: str,
        round_id: str,
        op: str,
        path: str,
        size_before: Optional[int] = None,
        size_after: Optional[int] = None,
        hash_before: Optional[str] = None,
        hash_after: Optional[str] = None,
        blob_stored: bool = False,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> str:
        """记一条文件操作。before/after hash + size 由 file_pipeline 计算填入。

        blob_stored=True 表示 hash_before/hash_after 在 blob 库中确实有可回退内容；
        二进制/超限文件则为 False，diff/restore 接口据此判断能否回溯。
        """
        size_delta = None
        if size_before is not None and size_after is not None:
            size_delta = size_after - size_before
        rec = CheckpointRecord(
            id=self._new_id(),
            kind=RecordKind.FILE_OP,
            session_id=session_id,
            round_id=round_id,
            seq=0,
            status=status,
            error=error,
            payload=FileOpRecord(
                op=op,
                path=path,
                size_before=size_before,
                size_after=size_after,
                hash_before=hash_before,
                hash_after=hash_after,
                size_delta=size_delta,
                blob_stored=blob_stored,
            ).model_dump(mode="json"),
        )
        self._emit(rec)
        return rec.id

    def emit_command(
        self,
        *,
        session_id: str,
        round_id: str,
        cmd: str,
        cwd: str = "",
        exit_code: Optional[int] = None,
        stdout_tail: str = "",
        stderr_tail: str = "",
        duration_ms: int = 0,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> str:
        """记一条命令执行。"""
        rec = CheckpointRecord(
            id=self._new_id(),
            kind=RecordKind.COMMAND,
            session_id=session_id,
            round_id=round_id,
            seq=0,
            status=status,
            error=error,
            payload=CommandRecord(
                cmd=cmd,
                cwd=cwd,
                exit_code=exit_code,
                stdout_tail=stdout_tail[-500:],
                stderr_tail=stderr_tail[-500:],
                duration_ms=duration_ms,
            ).model_dump(mode="json"),
        )
        self._emit(rec)
        return rec.id

    def emit_mcp_call(
        self,
        *,
        session_id: str,
        round_id: str,
        server_id: str,
        tool_name: str,
        arguments: dict,
        result_snippet: str = "",
        result_truncated: bool = False,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> str:
        """记一条 MCP server 工具调用。"""
        rec = CheckpointRecord(
            id=self._new_id(),
            kind=RecordKind.MCP_CALL,
            session_id=session_id,
            round_id=round_id,
            seq=0,
            status=status,
            error=error,
            payload=McpCallRecord(
                server_id=server_id,
                tool_name=tool_name,
                arguments=arguments or {},
                result_snippet=result_snippet[:500],
                result_truncated=result_truncated or len(result_snippet) > 500,
            ).model_dump(mode="json"),
        )
        self._emit(rec)
        return rec.id

    def emit_round(
        self,
        *,
        session_id: str,
        round_id: str,
        user_msg: str = "",
        assistant_text: str = "",
        reasoning: str = "",
        tool_count: int = 0,
        failed_tools: int = 0,
        duration_ms: int = 0,
        status: str = "ok",
        error: Optional[str] = None,
    ) -> str:
        """记一条 round 总结点 —— 写在每轮 final assistant 输出之后。"""
        rec = CheckpointRecord(
            id=self._new_id(),
            kind=RecordKind.ROUND,
            session_id=session_id,
            round_id=round_id,
            seq=0,
            status=status,
            error=error,
            payload=RoundRecord(
                user_msg_snippet=user_msg[:200],
                user_msg_truncated=len(user_msg) > 200,
                assistant_text_snippet=assistant_text[:200],
                assistant_truncated=len(assistant_text) > 200,
                reasoning_snippet=reasoning[:200],
                tool_count=tool_count,
                failed_tools=failed_tools,
                duration_ms=duration_ms,
            ).model_dump(mode="json"),
        )
        self._emit(rec)
        return rec.id

    # ── 读 ──────────────────────────────────────────────────────
    def timeline(self, session_id: str, limit: int = 200, offset: int = 0,
                 include_superseded: bool = False) -> list[dict]:
        return self.store.list_by_session(session_id, limit=limit, offset=offset,
                                          include_superseded=include_superseded)

    def summary(self, session_id: str) -> dict:
        return self.store.summary_by_session(session_id)

    def get_blob(self, hash: str) -> Optional[str]:
        """按 hash 读回 blob 内容（diff / restore 用）。无此 hash 返回 None。"""
        return self.blob_store.get(hash)

    def put_blob(self, content: str) -> str:
        """存一份内容到 blob 库，返回 hash。超限或非文本不进行判断由调用方负责。"""
        return self.blob_store.put(content)

    def prune(self, session_id: str, keep_recent_rounds: int = 50) -> dict:
        """清理某 session 过期 round 及其记录；顺带回收孤儿 blob。

        返回 {"deleted_records": n, "deleted_blobs": m, "rows_scanned": k}。
        """
        pruned = self.store.prune_session(session_id, keep_recent_rounds)
        orphans = self.prune_orphan_blobs()
        return {**pruned, "deleted_blobs": orphans["deleted_blobs"]}

    def prune_orphan_blobs(self) -> dict:
        """回收不被任何 record 引用的 blob 文件。回来 {"deleted_blobs": n, "scanned": k}。"""
        return self.store.prune_orphan_blobs(self.blob_store)


# ── 单例 ─────────────────────────────────────────────────────────────
_INSTANCE: Optional[CheckpointRecorder] = None



def init_recorder(db_path: str, blob_dir: Optional[str] = None) -> CheckpointRecorder:
    """应用启动时调用一次，注入 db_path（与 memory.db 同库或独立）。

    blob_dir 可选；不传则默认在 db_path 同级建 `checkpoint_blobs/`。
    """
    global _INSTANCE
    store = CheckpointStore(db_path)
    _INSTANCE = CheckpointRecorder(
        store,
        BlobStore(blob_dir or os.path.join(os.path.dirname(os.path.abspath(db_path)), "checkpoint_blobs")),
    )
    return _INSTANCE


def get_recorder() -> CheckpointRecorder:
    """拿全局单例。未初始化时抛 RuntimeError —— 强制走 init_recorder。"""
    if _INSTANCE is None:
        raise RuntimeError(
            "CheckpointRecorder 未初始化；请在 application/state.py "
            "启动时调用 Symbix_sdk.checkpoint.init_recorder(db_path)"
        )
    return _INSTANCE
