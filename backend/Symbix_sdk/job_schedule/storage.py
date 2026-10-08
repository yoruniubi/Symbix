from __future__ import annotations
import os
import sqlite3
import json
from datetime import datetime
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_meta (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    trigger_config TEXT NOT NULL,
    prompt TEXT NOT NULL,
    session_id TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    auto_safe INTEGER NOT NULL DEFAULT 1,
    last_run_time TEXT,
    last_status TEXT,
    last_error TEXT,
    completed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    run_time TEXT NOT NULL,
    status TEXT NOT NULL,
    output_snippet TEXT DEFAULT '',
    error TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_job_history_job ON job_history(job_id, run_time DESC);
"""


class JobStorage:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript(_SCHEMA)
            # 老库补列(建表语句对已存在的表不生效)
            try:
                c.execute("ALTER TABLE job_meta ADD COLUMN completed INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass      # 列已存在

    # ---- job_meta CRUD ----
    def upsert_meta(self, job: dict) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO job_meta(id,name,trigger_type,trigger_config,prompt,session_id,enabled,auto_safe,last_run_time,last_status,last_error,completed)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, trigger_type=excluded.trigger_type,
                     trigger_config=excluded.trigger_config, prompt=excluded.prompt,
                     session_id=excluded.session_id, enabled=excluded.enabled,
                     auto_safe=excluded.auto_safe, last_run_time=excluded.last_run_time,
                     last_status=excluded.last_status, last_error=excluded.last_error,
                     completed=excluded.completed""",
                (
                    job["id"], job["name"], job["trigger_type"],
                    json.dumps(job["trigger_config"], ensure_ascii=False),
                    job["prompt"], job.get("session_id"),
                    int(job.get("enabled", True)), int(job.get("auto_safe", True)),
                    job.get("last_run_time"), job.get("last_status"), job.get("last_error"),
                    int(job.get("completed", False)),
                ),
            )

    def get_meta(self, job_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM job_meta WHERE id=?", (job_id,)).fetchone()
        return self._row_to_meta(row) if row else None

    def list_meta(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM job_meta ORDER BY id").fetchall()
        return [self._row_to_meta(r) for r in rows]

    def delete_meta(self, job_id: str) -> bool:
        with self._conn() as c:
            cur = c.execute("DELETE FROM job_meta WHERE id=?", (job_id,))
            return cur.rowcount > 0

    def delete_history(self, job_id: str) -> None:
        """删除某 job 的全部历史记录(随 job 删除一并清理)。"""
        with self._conn() as c:
            try:
                c.execute("DELETE FROM job_history WHERE job_id=?", (job_id,))
            except sqlite3.Error:
                pass

    def update_status(self, job_id: str, status: str, error: Optional[str], run_time: datetime) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE job_meta SET last_run_time=?, last_status=?, last_error=? WHERE id=?",
                (run_time.isoformat(), status, error, job_id),
            )

    def set_completed(self, job_id: str, completed: bool = True, disable: bool = True) -> None:
        """标记一次性任务「已跑过」,同时置 enabled=0(已触发过就不必重排)。"""
        with self._conn() as c:
            if disable:
                c.execute("UPDATE job_meta SET completed=?, enabled=0 WHERE id=?",
                          (int(completed), job_id))
            else:
                c.execute("UPDATE job_meta SET completed=? WHERE id=?", (int(completed), job_id))

    def _row_to_meta(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        d["trigger_config"] = json.loads(d["trigger_config"]) if d["trigger_config"] else {}
        d["enabled"] = bool(d["enabled"])
        d["auto_safe"] = bool(d["auto_safe"])
        d["completed"] = bool(d.get("completed") or 0)
        return d

    # ---- history ----
    def add_history(self, job_id: str, run_time: datetime, status: str, output_snippet: str = "", error: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO job_history(job_id,run_time,status,output_snippet,error) VALUES(?,?,?,?,?)",
                (job_id, run_time.isoformat(), status, output_snippet, error),
            )

    def list_history(self, job_id: str, limit: int = 20) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM job_history WHERE job_id=? ORDER BY run_time DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
