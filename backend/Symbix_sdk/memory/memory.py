import sqlite3
import os
import json
from datetime import datetime
from threading import Lock

# 工具 memo 落库用的内部角色名。**不能**用 "tool":OpenAI 兼容协议里
# role="tool" 必须带 tool_call_id 并与 assistant 的 tool_calls 配对,
# 而从历史里读回来的 memo 没有这些字段,发给上游会被判 400。
TOOL_MEMO_ROLE = "tool_memo"

# 上游失败时后端写进 assistant 位置的占位文本特征。这些**不是模型说的话**,
# 读历史时必须挡住:否则模型会对着「[错误] HTTP 500」自我安慰、复述报错,
# 用户看到的就是「怎么修都没用」。老库里已经有这类脏数据,所以判定放在
# 读取侧(而不是只保证新代码不写),新旧一并兼容,不用清库。
_UPSTREAM_ERROR_MARKERS = (
    "[错误] HTTP",          # 早期版本:纯占位
    "[本轮执行被打断:",     # 现在:带工具轮进度的收尾
    "上游返回为空(本轮未完成)",
)

# 摘要里出现这些片段的**整行**要剥掉。梗概见下:压缩提示曾经明确要求
# 模型把「报错原文」抄进摘要,于是 `[错误] HTTP 429/500` 这类文本被
# 当成 system 消息每轮重发上游,累积后踩中上游长上下文审核器
# (hashlinear_model,confidence 卡在 0.700~0.702),导致该会话**每轮必 500**。
# 实测:剥掉这些行之后同一个会话立刻恢复正常。
_SUMMARY_NOISE_MARKERS = _UPSTREAM_ERROR_MARKERS + (
    "报错原文",             # 「## 关键上下文」里那一行
    "失败命令原文",
    "MODERATION_BLOCKED",
)
# 摘要长度兜底。摘要是滚动重写的(每次压缩把旧摘要喂回去),不设上限会
# 越滚越大,既费 token 又更容易触发上游长上下文审核器。
#
# 3000 这个数来自实测:同一个会话,摘要 5818 字时 3/3 被审核拦(confidence
# 0.700~0.702,正好压在阈值上),5000 字以下 3/3 放行。留足安全余量取 3000。
# 注意这个审核器是特征哈希线性模型,对原文长度极敏感 —— 同一段文本加 1 个
# 字符就翻成拦截,加 20 个字符又变回放行,所以**不能贴着边界设**。
SUMMARY_MAX_CHARS = 3000


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

    def get_history(self, session_id: str, limit: int = 20,
                    roles: tuple[str, ...] | None = None) -> list[dict]:
        """原始历史（最新 limit 条，正序）。

        roles 为 None 时返回全部角色；前端 /history 与弹幕去重要传
        ("user", "assistant")，否则会把 role="tool" 的工具 memo 也吐出去。
        """
        sql = "SELECT role, content FROM messages WHERE session_id = ?"
        params: list = [session_id]
        if roles:
            sql += " AND role IN (%s)" % ",".join("?" * len(roles))
            params.extend(roles)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cursor = self.conn.execute(sql, tuple(params))
            rows = cursor.fetchall()[::-1]
        return [{"role": r, "content": c} for r, c in rows]

    def get_history_with_ids(self, session_id: str, limit: int = 100,
                             roles: tuple[str, ...] | None = None) -> list[dict]:
        """带 id 的历史，用于压缩判断。

        roles 为 None 时包含 tool memo —— 摘要正需要这些工具细节。
        """
        sql = "SELECT id, role, content FROM messages WHERE session_id = ?"
        params: list = [session_id]
        if roles:
            sql += " AND role IN (%s)" % ",".join("?" * len(roles))
            params.extend(roles)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            cursor = self.conn.execute(sql, tuple(params))
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

    @staticmethod
    def is_upstream_error_placeholder(content: str) -> bool:
        """判断这条 assistant 内容是不是「后端写的报错占位」而非模型回复。"""
        text = (content or "").strip()
        return any(m in text for m in _UPSTREAM_ERROR_MARKERS)

    @staticmethod
    def sanitize_summary_for_upstream(
        summary: str, max_chars: int = SUMMARY_MAX_CHARS
    ) -> str:
        """把摘要里的「报错噪音」剥掉,再夹一个长度上限。

        摘要会作为 system 消息**每一轮**发给上游。里面抄了 `[错误] HTTP 429`
        这类原文时,文本一多就会踩中上游长上下文审核器(MODERATION_BLOCKED),
        该会话从此每轮必 500 —— 用户看到的就是「怎么修都没用」。
        这些报错信息对续跑没有价值(该知道的进度在 task_progress /
        tool_digest 里都有),直接剥掉最安全。

        只删整行,不删半句,免得把行内其他有用内容一起毁掉。
        """
        if not summary:
            return ""
        kept: list[str] = []
        for line in summary.splitlines():
            if any(m in line for m in _SUMMARY_NOISE_MARKERS):
                continue
            kept.append(line)
        out = "\n".join(kept).strip()
        if len(out) > max_chars:
            out = out[:max_chars].rstrip() + "\n…(摘要过长,已截断)"
        return out

    @staticmethod
    def as_upstream_message(msg: dict) -> dict | None:
        """把库里的消息转成能直接发给上游的 messages 元素。

        工具 memo 不能以 role="tool" 发出去(缺 tool_call_id 会被判 400),
        这里改成 user 并加前缀说明。不用 system 是因为 system 一变,
        上游的 prompt cache 就整段失效。

        报错占位降级处理(**返回 None 表示整条丢弃**):
        - 整段都是占位的 assistant 轮 → 丢。模型不需要「自己上次失败了」,
          上一轮 user 还在,任务本身没丢;留着它只会招来自我安慰式复述。
        - 模型说了话但末尾被追加了占位 → 截掉占位保留正文。
        """
        role = msg.get("role")
        content = msg.get("content", "") or ""
        if role in (TOOL_MEMO_ROLE, "tool"):
            return {
                "role": "user",
                "content": f"[工具执行记录,供你继续这轮任务时参考]\n{content}",
            }
        if role == "assistant":
            stripped = content.strip()
            if not stripped:
                return None
            if ConversationMemory.is_upstream_error_placeholder(stripped):
                # 找到最早出现的占位起点,截断它后面的部分
                cut = len(stripped)
                for marker in _UPSTREAM_ERROR_MARKERS:
                    pos = stripped.find(marker)
                    if pos != -1:
                        cut = min(cut, pos)
                head = stripped[:cut].rstrip()
                if not head:
                    return None
                return {"role": "assistant", "content": head}
        return {"role": role, "content": content}

    def get_compressed_history(
        self, session_id: str, recent_limit: int = 12
    ) -> list[dict]:
        """返回压缩后的上下文：
        - 若有摘要：[{role:system, content:摘要}, ...最近 recent_limit 条]
        - 若无摘要：最近 recent_limit 条

        返回的每一条都经过 as_upstream_message,可以直接进上游 messages。
        后端写的报错占位会被这里滤掉(见 as_upstream_message)。
        """
        summary_info = self.get_summary(session_id)
        # as_upstream_message 可能返回 None(整条是报错占位),过滤掉
        recent = [m for m in (self.as_upstream_message(x)
                              for x in self.get_history(session_id, limit=recent_limit))
                  if m is not None]

        if not summary_info or not summary_info.get("summary"):
            return recent

        # 摘要里的报错原文必须剥掉:它会作为 system 消息每轮重发上游,
        # 累积到一定量就踩中上游长上下文审核 → 该会话每轮必 500。
        clean_summary = self.sanitize_summary_for_upstream(summary_info["summary"])
        if not clean_summary:
            return recent

        # 摘要作为 system 角色的上下文前缀（兼容 OpenAI messages 格式）
        prefix = {
            "role": "system",
            "content": f"[对话历史摘要]\n{clean_summary}",
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