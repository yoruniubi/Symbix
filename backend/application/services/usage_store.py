from __future__ import annotations
import os
import json
import sqlite3
import threading
from datetime import datetime, timedelta, date
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,             -- Unix 秒(本地时钟)
    session_id TEXT DEFAULT '',
    model TEXT DEFAULT '',
    prompt INTEGER DEFAULT 0,        -- 估算:system+tools+history
    output INTEGER DEFAULT 0,        -- 估算:输出文本
    tools INTEGER DEFAULT 0,         -- 估算:工具 schema 注入
    total INTEGER DEFAULT 0,
    up_prompt INTEGER,               -- 上游真返回(可能为 NULL)
    up_completion INTEGER,
    up_total INTEGER,
    payload TEXT                   -- 完整 usage payload JSON(恢复会话末轮明细用)
);
CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);
"""

# 聚合列:估算口径与前端展示一致
_SUM_COLS = "COALESCE(SUM(prompt),0), COALESCE(SUM(output),0), COALESCE(SUM(tools),0), COALESCE(SUM(total),0), COUNT(*)"


class UsageStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
            # 旧库迁移:早期版本无 payload 列(幂等:已存在则报错忽略)
            try:
                c.execute("ALTER TABLE token_usage ADD COLUMN payload TEXT")
            except sqlite3.OperationalError:
                pass

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def record(
        self,
        ts: int,
        session_id: str,
        model: str,
        prompt: int,
        output: int,
        tools: int,
        total: int,
        up_prompt: Optional[int] = None,
        up_completion: Optional[int] = None,
        up_total: Optional[int] = None,
        payload: Optional[str] = None,
    ) -> None:
        """记一轮用量(每轮 done 只记一次,由调用方保证幂等)。"""
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO token_usage(ts,session_id,model,prompt,output,tools,total,"
                "up_prompt,up_completion,up_total,payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (ts, session_id, model, prompt, output, tools, total,
                 up_prompt, up_completion, up_total, payload),
            )

    def _sum_between(self, c: sqlite3.Connection, start: int, end: int) -> dict:
        row = c.execute(
            f"SELECT {_SUM_COLS} FROM token_usage WHERE ts >= ? AND ts < ?", (start, end)
        ).fetchone()
        return {"prompt": row[0], "output": row[1], "tools": row[2],
                "total": row[3], "calls": row[4]}

    def session_info(self, session_id: str) -> dict:
        """会话级恢复数据:末轮(数值列直读,payload 补明细)+ 会话累计。

        payload 只在 8.62 之后才有;老行数值列齐全,末轮基础数值不依赖它。
        """
        with self._conn() as c:
            row = c.execute(
                "SELECT prompt, output, tools, total, up_prompt, up_completion, up_total, payload "
                "FROM token_usage WHERE session_id = ? ORDER BY ts DESC, id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            total = c.execute(
                "SELECT COALESCE(SUM(prompt),0), COALESCE(SUM(output),0), "
                "COALESCE(SUM(total),0), COUNT(*) FROM token_usage WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        last = None
        if row:
            last = {"prompt": row[0], "output": row[1], "tools": row[2], "total": row[3]}
            if row[4] is not None:
                last["upstream"] = {"prompt_tokens": row[4], "completion_tokens": row[5],
                                    "total_tokens": row[6]}
            if row[7]:
                try:  # payload 里有更细的 system/history/estimated,合并覆盖
                    detail = json.loads(row[7])
                    if isinstance(detail, dict):
                        last.update({k: v for k, v in detail.items() if k not in last or k == "upstream"})
                except (ValueError, TypeError):
                    pass
        return {
            "last": last,
            "total": {"prompt": total[0], "output": total[1],
                      "total": total[2], "calls": total[3]},
        }

    def summary(self, days: int = 30) -> dict:
        """日/周/月汇总 + 最近 N 天逐日明细(含零天,画柱状图用)。"""
        now = datetime.now()
        today_start = int(datetime.combine(now.date(), datetime.min.time()).timestamp())
        # 周一为一周起点;month 起点直接取 1 号
        week_start = today_start - now.weekday() * 86400
        month_start = int(datetime.combine(now.date().replace(day=1),
                                           datetime.min.time()).timestamp())
        horizon_start = today_start - (days - 1) * 86400
        with self._conn() as c:
            out = {
                "today": self._sum_between(c, today_start, today_start + 86400),
                "week": self._sum_between(c, week_start, today_start + 86400),
                "month": self._sum_between(c, month_start, today_start + 86400),
                "days": [],
            }
            rows = c.execute(
                "SELECT ts, prompt, output, tools, total FROM token_usage WHERE ts >= ?",
                (horizon_start,),
            ).fetchall()
        # 数据量小(30 天),取回 Python 按本地日期聚合,避开 SQL 时区换算坑
        agg: dict = {}
        for r in rows:
            d = datetime.fromtimestamp(r[0]).date().isoformat()
            a = agg.setdefault(d, [0, 0, 0, 0, 0])
            a[0] += r[1]; a[1] += r[2]; a[2] += r[3]; a[3] += r[4]; a[4] += 1
        d0 = date.fromtimestamp(horizon_start)
        for i in range(days):
            day = (d0 + timedelta(days=i)).isoformat()
            a = agg.get(day, [0, 0, 0, 0, 0])
            out["days"].append({
                "date": day,
                "prompt": a[0], "output": a[1], "tools": a[2],
                "total": a[3], "calls": a[4],
            })
        return out
