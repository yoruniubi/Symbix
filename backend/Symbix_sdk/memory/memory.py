import sqlite3
import os
from datetime import datetime
from threading import Lock

class ConversationMemory:
    """基于 SQLite 的对话历史存储（线程安全）"""

    def __init__(self, db_path: str = "memory.db"):
        self.db_path = db_path
        # 确保数据库所在目录存在
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
            # 为 session_id 创建索引以加速查询
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session_id 
                ON messages(session_id)
            """)
            self.conn.commit()

    def add(self, session_id: str, role: str, content: str):
        with self._lock:
            self.conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, content, datetime.now().isoformat()),
            )
            self.conn.commit()

    def get_history(self, session_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            cursor = self.conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            )
            rows = cursor.fetchall()[::-1]  # 反转回正序
        return [{"role": r, "content": c} for r, c in rows]

    def clear_session(self, session_id: str):
        """清除指定 session 的所有记录"""
        with self._lock:
            self.conn.execute(
                "DELETE FROM messages WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
