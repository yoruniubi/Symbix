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

    def list_by_session(self, session_id: str, limit: int = 200, offset: int = 0) -> list[dict]:
        """按 session 列时间线，按 seq 升序。"""
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                """SELECT id, kind, ts, round_id, seq, status, error, payload
                     FROM checkpoint_records
                    WHERE session_id = ?
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

    def list_by_round(self, session_id: str, round_id: str) -> list[dict]:
        """某 round 的全部事件。"""
        with self._lock:
            conn = self._ensure_conn()
            rows = conn.execute(
                """SELECT id, kind, ts, round_id, seq, status, error, payload
                     FROM checkpoint_records
                    WHERE session_id = ? AND round_id = ?
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

    def close(self):
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
