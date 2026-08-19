"""Checkpoint 持久化 + 单例 Recorder。

存储设计：单表 `checkpoint_records`，所有 kind 共用 schema，按 (session_id, round_id, seq) 排序。
- payload 用 json.dumps 存 TEXT；查询时不解析 payload（除非前端要，再解）。
- 复用 backend `application/state.py` 里 `memory.db` 同库 —— 减少连接数、跨表查询方便。
- 线程安全：单个 sqlite connection + threading.Lock，跟 MemoryStore 一致风格。
"""
from __future__ import annotations

import os
import json
import sqlite3
import threading
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


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checkpoint_records (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,              -- tool_call / file_op / command / mcp_call / round
    ts          TEXT NOT NULL,              -- ISO8601 UTC
    session_id  TEXT NOT NULL,
    round_id    TEXT NOT NULL,
    seq         INTEGER NOT NULL,           -- session 内全局递增
    status      TEXT NOT NULL DEFAULT 'ok',
    error       TEXT,
    payload     TEXT NOT NULL DEFAULT '{}'  -- json.dumps(model_dump(mode='json'))
);
CREATE INDEX IF NOT EXISTS idx_chk_session_round ON checkpoint_records(session_id, round_id, seq);
CREATE INDEX IF NOT EXISTS idx_chk_session_ts    ON checkpoint_records(session_id, ts);
CREATE INDEX IF NOT EXISTS idx_chk_kind          ON checkpoint_records(kind);
"""


class CheckpointStore:
    """SQLite 存储。简单写，不做高级特性。

    与 MemoryStore 同库的好处：跨表 join、备份策略统一。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.Lock()
        self._seq_counter: dict[str, int] = {}     # session_id -> last seq
        # 保证 parent dir 存在
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._ensure_conn()

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        # check_same_thread=False —— 配合外层 Lock 保证线程安全
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # 启用 WAL 模式减少磁盘锁竞争（memory.db 也已 WAL）
        try:
            self._conn.execute("PRAGMA journal_mode=WAL;")
        except sqlite3.OperationalError:
            pass
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()
        return self._conn

    def _next_seq(self, session_id: str) -> int:
        """session 内自增 seq：启动 / 新 session 时从库拉 MAX(seq) 兜底，避免重启后从 0 重置与既有 row 撞。"""
        cur_seq = self._seq_counter.get(session_id)
        if cur_seq is None:
            with self._lock:
                conn = self._ensure_conn()
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS m FROM checkpoint_records WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            cur_seq = int(row["m"]) if row else 0
        cur_seq += 1
        self._seq_counter[session_id] = cur_seq
        return cur_seq

    def insert(self, record: CheckpointRecord) -> None:
        if record.seq <= 0:
            record.seq = self._next_seq(record.session_id)
        with self._lock:
            conn = self._ensure_conn()
            conn.execute(
                """INSERT INTO checkpoint_records
                       (id, kind, ts, session_id, round_id, seq, status, error, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id,
                    record.kind.value,
                    record.ts,
                    record.session_id,
                    record.round_id,
                    record.seq,
                    record.status,
                    record.error,
                    json.dumps(record.payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def list_by_session(self, session_id: str, limit: int = 200, offset: int = 0,
                       include_superseded: bool = False) -> list[dict]:
        """按 session 列时间线，按 seq 升序。默认过滤掉 superseded 记录。"""
        with self._lock:
            conn = self._ensure_conn()
            if include_superseded:
                rows = conn.execute(
                    """SELECT id, kind, ts, round_id, seq, status, error, payload
                         FROM checkpoint_records
                        WHERE session_id = ?
                        ORDER BY seq ASC
                        LIMIT ? OFFSET ?""",
                    (session_id, limit, offset),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, kind, ts, round_id, seq, status, error, payload
                         FROM checkpoint_records
                        WHERE session_id = ? AND status != 'superseded'
                        ORDER BY seq ASC
                        LIMIT ? OFFSET ?""",
                    (session_id, limit, offset),
                ).fetchall()
        out = []
        for r in rows:
            obj = dict(r)
            try:
                obj["payload"] = json.loads(obj.get("payload") or "{}")
            except json.JSONDecodeError:
                obj["payload"] = {}
            out.append(obj)
        return out

    def list_by_round(self, session_id: str, round_id: str,
                       include_superseded: bool = False) -> list[dict]:
        """某 round 的全部事件。默认过滤掉 superseded。"""
        with self._lock:
            conn = self._ensure_conn()
            if include_superseded:
                rows = conn.execute(
                    """SELECT id, kind, ts, round_id, seq, status, error, payload
                         FROM checkpoint_records
                        WHERE session_id = ? AND round_id = ?
                        ORDER BY seq ASC""",
                    (session_id, round_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, kind, ts, round_id, seq, status, error, payload
                         FROM checkpoint_records
                        WHERE session_id = ? AND round_id = ? AND status != 'superseded'
                        ORDER BY seq ASC""",
                    (session_id, round_id),
                ).fetchall()
        out = []
        for r in rows:
            obj = dict(r)
            try:
                obj["payload"] = json.loads(obj.get("payload") or "{}")
            except json.JSONDecodeError:
                obj["payload"] = {}
            out.append(obj)
        return out

    def summary_by_session(self, session_id: str) -> dict:
        """一个 session 一镜头 overview —— 喂给前端时间线头部。"""
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(
                """SELECT COUNT(*) AS total,
                          MIN(ts) AS first_ts,
                          MAX(ts) AS last_ts,
                          SUM(CASE WHEN kind='tool_call'  THEN 1 ELSE 0 END) AS tool_call_n,
                          SUM(CASE WHEN kind='file_op'    THEN 1 ELSE 0 END) AS file_op_n,
                          SUM(CASE WHEN kind='command'    THEN 1 ELSE 0 END) AS command_n,
                          SUM(CASE WHEN kind='mcp_call'   THEN 1 ELSE 0 END) AS mcp_call_n,
                          SUM(CASE WHEN kind='round'      THEN 1 ELSE 0 END) AS round_n,
                          SUM(CASE WHEN status='error'    THEN 1 ELSE 0 END) AS error_n
                     FROM checkpoint_records
                    WHERE session_id = ?""",
                (session_id,),
            ).fetchone()
        return dict(row) if row else {}

    def mark_round_superseded(self, session_id: str, round_id: str) -> int:
        """把某 round 下所有记录 status 改为 'superseded'。返回受影响行数。"""
        with self._lock:
            conn = self._ensure_conn()
            cur = conn.execute(
                """UPDATE checkpoint_records
                      SET status = 'superseded'
                    WHERE session_id = ? AND round_id = ?""",
                (session_id, round_id),
            )
            conn.commit()
            return cur.rowcount

    def get_record(self, record_id: str) -> Optional[dict]:
        """按主键查单条记录。"""
        with self._lock:
            conn = self._ensure_conn()
            row = conn.execute(
                """SELECT id, kind, ts, session_id, round_id, seq, status, error, payload
                     FROM checkpoint_records WHERE id = ?""",
                (record_id,),
            ).fetchone()
        if not row:
            return None
        obj = dict(row)
        try:
            obj["payload"] = json.loads(obj.get("payload") or "{}")
        except json.JSONDecodeError:
            obj["payload"] = {}
        return obj

    def prune_session(self, session_id: str, keep_recent_rounds: int = 50) -> dict:
        """保留最近 N 个 round，删除更早 round 的所有记录。返回删除统计。"""
        with self._lock:
            conn = self._ensure_conn()
            # 取该 session 所有 round_id，按 MAX(seq) 倒序
            round_rows = conn.execute(
                """SELECT round_id, MAX(seq) AS max_seq
                     FROM checkpoint_records
                    WHERE session_id = ?
                    GROUP BY round_id
                    ORDER BY max_seq DESC""",
                (session_id,),
            ).fetchall()
            all_rounds = [r["round_id"] for r in round_rows]
            if len(all_rounds) <= keep_recent_rounds:
                return {"deleted_records": 0, "rounds_total": len(all_rounds),
                        "rounds_kept": len(all_rounds)}
            to_drop = all_rounds[keep_recent_rounds:]
            placeholders = ",".join("?" for _ in to_drop)
            cur = conn.execute(
                f"""DELETE FROM checkpoint_records
                      WHERE session_id = ? AND round_id IN ({placeholders})""",
                (session_id, *to_drop),
            )
            conn.commit()
            return {"deleted_records": cur.rowcount,
                    "rounds_total": len(all_rounds),
                    "rounds_kept": keep_recent_rounds,
                    "rounds_dropped": len(to_drop)}

    def prune_orphan_blobs(self, blob_store) -> dict:
        """扫描全表 payload 里引用的 hash，删掉 blob 库中不再被引用的文件。"""
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                """SELECT payload FROM checkpoint_records
                    WHERE kind = 'file_op'"""
            ).fetchall()
        referenced: set[str] = set()
        for r in rows:
            try:
                payload = json.loads(r["payload"] or "{}")
            except json.JSONDecodeError:
                continue
            for key in ("hash_before", "hash_after"):
                h = payload.get(key)
                if isinstance(h, str) and h:
                    referenced.add(h)
        all_hashes = blob_store.list_all_hashes()
        orphans = all_hashes - referenced
        deleted = 0
        for h in orphans:
            blob_store.delete(h)
            deleted += 1
        return {"deleted_blobs": deleted, "scanned": len(all_hashes),
                "referenced": len(referenced)}

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
