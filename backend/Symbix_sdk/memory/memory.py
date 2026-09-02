import sqlite3
import os
import json
from datetime import datetime
from threading import Lock


class ConversationMemory:
    """基于 SQLite 的对话历史存储（线程安全）

    额外能力：
    - session_summaries：会话阶段性摘要（上下文压缩）
    - user_profile：跨会话用户画像（职业、项目、偏好等）
    """

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id
                ON messages(session_id)
            """)
            # 会话摘要表
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    covered_until_id INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            # 用户画像表（跨会话）
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS user_profile (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            self.conn.commit()

    # ─── 消息 ───────────────────────────────────────────────

    def add(self, session_id: str, role: str, content: str) -> int:
        """写入一条消息，返回插入的 row id"""
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, datetime.now().isoformat()),
            )
            self.conn.commit()
            return cur.lastrowid

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        """原始历史（最新 limit 条，正序）"""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()[::-1]
        return [{"role": r, "content": c} for r, c in rows]

    def get_history_with_ids(self, session_id: str, limit: int = 100) -> list[dict]:
        """带 id 的历史，用于压缩判断"""
        with self._lock:
            cursor = self.conn.execute(
                "SELECT id, role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()[::-1]
        return [{"id": i, "role": r, "content": c} for i, r, c in rows]

    def count_messages(self, session_id: str) -> int:
        with self._lock:
            cur = self.conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (session_id,),
            )
            return cur.fetchone()[0]

    def get_messages_range(
        self, session_id: str, after_id: int = 0, before_id: int | None = None, limit: int = 50
    ) -> list[dict]:
        """获取 id 在 (after_id, before_id] 之间的消息"""
        with self._lock:
            if before_id is not None:
                cursor = self.conn.execute(
                    """SELECT id, role, content FROM messages
                       WHERE session_id = ? AND id > ? AND id <= ?
                       ORDER BY id ASC LIMIT ?""",
                    (session_id, after_id, before_id, limit),
                )
            else:
                cursor = self.conn.execute(
                    """SELECT id, role, content FROM messages
                       WHERE session_id = ? AND id > ?
                       ORDER BY id ASC LIMIT ?""",
                    (session_id, after_id, limit),
                )
            rows = cursor.fetchall()
        return [{"id": i, "role": r, "content": c} for i, r, c in rows]

    def clear_session(self, session_id: str):
        """清除指定 session 的消息、摘要和 checkpoint 记录（含孤儿 blob 文件）"""
        with self._lock:
            # 先收集本 session 引用的 blob hash（checkpoint_records.payload 里 hash_before/hash_after）
            my_hashes = self._collect_blob_hashes(session_id)
            self.conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM session_summaries WHERE session_id = ?", (session_id,))
            # checkpoint_records 与对话历史强绑定，删除对话时一并清除
            self.conn.execute("DELETE FROM checkpoint_records WHERE session_id = ?", (session_id,))
            self.conn.commit()
            # 删除后全库剩余的 blob 引用；本 session 独有且不再被引用的 hash → 孤儿，删文件
            if my_hashes:
                remaining = self._collect_blob_hashes(None)
                orphans = my_hashes - remaining
                if orphans:
                    self._delete_blob_files(orphans)

    def _collect_blob_hashes(self, session_id: str | None) -> set[str]:
        """从 checkpoint_records 的 payload 里收集 blob hash（内容寻址，12 位）。
        session_id=None 时扫全库。"""
        hashes: set[str] = set()
        try:
            if session_id is not None:
                rows = self.conn.execute(
                    "SELECT payload FROM checkpoint_records WHERE session_id = ?",
                    (session_id,),
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT payload FROM checkpoint_records").fetchall()
            for (payload_json,) in rows:
                try:
                    payload = json.loads(payload_json)
                    for key in ("hash_before", "hash_after"):
                        h = payload.get(key)
                        if isinstance(h, str) and len(h) == 12:
                            hashes.add(h)
                except Exception:
                    continue
        except Exception:
            pass
        return hashes

    def _delete_blob_files(self, hashes: set[str]):
        """删除 blob 文件。blob 目录与 memory.db 同级为 checkpoint_blobs/。"""
        if not hashes:
            return
        try:
            from Symbix_sdk.checkpoint.blob_store import BlobStore
            blob_dir = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "checkpoint_blobs")
            store = BlobStore(blob_dir)
            for h in hashes:
                store.delete(h)
        except Exception as e:
            print(f"[Memory] blob cleanup failed: {e}")

    # ─── 上下文压缩 / 摘要 ──────────────────────────────────

    def get_summary(self, session_id: str) -> dict | None:
        """返回 {summary, covered_until_id} 或 None"""
        with self._lock:
            cur = self.conn.execute(
                "SELECT summary, covered_until_id FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {"summary": row[0], "covered_until_id": row[1]}

    def set_summary(self, session_id: str, summary: str, covered_until_id: int):
        with self._lock:
            self.conn.execute(
                """INSERT INTO session_summaries (session_id, summary, covered_until_id, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     summary = excluded.summary,
                     covered_until_id = excluded.covered_until_id,
                     updated_at = excluded.updated_at""",
                (session_id, summary, covered_until_id, datetime.now().isoformat()),
            )
            self.conn.commit()

    def get_compressed_history(
        self, session_id: str, recent_limit: int = 12
    ) -> list[dict]:
        """返回压缩后的上下文：
        - 若有摘要：[{role:system, content:摘要}, ...最近 recent_limit 条]
        - 若无摘要：最近 recent_limit 条
        """
        summary_info = self.get_summary(session_id)
        recent = self.get_history(session_id, limit=recent_limit)

        if not summary_info or not summary_info.get("summary"):
            return recent

        # 摘要作为 system 角色的上下文前缀（兼容 OpenAI messages 格式）
        prefix = {
            "role": "system",
            "content": f"[对话历史摘要]\n{summary_info['summary']}",
        }
        return [prefix] + recent

    # ─── 用户画像 ───────────────────────────────────────────

    def get_profile(self) -> dict[str, str]:
        """返回全部用户画像 {key: value}"""
        with self._lock:
            cur = self.conn.execute("SELECT key, value FROM user_profile")
            rows = cur.fetchall()
        return {k: v for k, v in rows}

    def set_profile_fact(self, key: str, value: str):
        """写入/更新一条画像事实"""
        key = key.strip()
        value = value.strip()
        if not key or not value:
            return
        with self._lock:
            self.conn.execute(
                """INSERT INTO user_profile (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                     value = excluded.value,
                     updated_at = excluded.updated_at""",
                (key, value, datetime.now().isoformat()),
            )
            self.conn.commit()

    def set_profile_facts(self, facts: dict[str, str]):
        """批量写入画像"""
        for k, v in facts.items():
            self.set_profile_fact(k, v)

    def delete_profile_fact(self, key: str):
        with self._lock:
            self.conn.execute("DELETE FROM user_profile WHERE key = ?", (key,))
            self.conn.commit()

    def get_profile_prompt(self) -> str:
        """格式化为可注入 system_prompt 的文本"""
        profile = self.get_profile()
        if not profile:
            return ""
        lines = [f"- {k}: {v}" for k, v in profile.items()]
        return "【关于用户的已知信息】\n" + "\n".join(lines)

    def close(self):
        self.conn.close()