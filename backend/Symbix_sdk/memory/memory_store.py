"""
MemoryStore — 原子记忆存储 + BM25 + 字符n-gram 检索
v2：零外部 embedding API，纯本地计算。
"""
import sqlite3
import re
import json
import asyncio
from typing import Optional, Any
from threading import Lock
from datetime import datetime, timezone

import jieba
from rank_bm25 import BM25Okapi


# ═══════════════════════════════════════════════════════════════════
# 停用词表（中文常用 + 英文常用）
# ═══════════════════════════════════════════════════════════════════

_STOP_WORDS: set[str] = {
    # 中文
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "什么", "怎么", "如何", "为什么", "因为", "所以", "但是", "然而",
    "可以", "这个", "那个", "如果", "的话", "吧", "吗", "呢", "啊", "嘛",
    "哦", "嗯",
    "被", "把", "让", "从", "对", "与", "或", "且", "向",
    "已", "还", "又", "再", "能", "能够", "应该", "可能", "可以",
    "多", "少", "更", "最", "非常", "比较", "特别", "相当", "有点",
    "已经", "正在", "将要", "曾经", "一直", "总是", "偶尔", "经常",
    "需要", "想要", "希望", "觉得", "认为", "知道", "了解", "明白",
    "比如", "例如", "包括", "除了", "另外", "此外", "然后", "接着",
    "目前", "现在", "当时", "刚才", "最近", "以前", "以后", "将来",
    "今天", "明天", "昨天", "今年", "去年", "明年",
    "关于", "对于", "至于", "按照", "根据", "经过", "通过",
    "里面", "外面", "上面", "下面", "前面", "后面",
    "时候", "地方", "东西", "事情", "情况", "关系", "问题",
    # 英文
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having", "do", "does", "did", "doing",
    "will", "would", "could", "should", "may", "might", "must", "shall",
    "can", "just", "not", "no", "nor",
    "and", "or", "but", "if", "else", "when", "where", "which", "who",
    "whom", "this", "that", "these", "those", "it", "its", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "so", "than", "too", "very",
    "about", "above", "after", "again", "against", "below", "between",
    "by", "for", "from", "in", "into", "of", "off", "on", "out",
    "over", "through", "to", "under", "up", "with",
    "here", "there", "now", "then", "also", "however", "therefore",
    "my", "your", "his", "her", "our", "their", "me", "him", "us", "them",
    "am", "at", "as", "because", "before", "during", "since", "while",
    "let", "go", "we", "you", "he", "she", "they", "what",
}

# 合法 category 枚举
_VALID_CATEGORIES: set[str] = {
    "identity", "preference", "habit", "goal", "constraint", "other",
}


# ═══════════════════════════════════════════════════════════════════
# Extraction prompt
# ═══════════════════════════════════════════════════════════════════

EXTRACTION_PROMPT = """你是一个记忆提取器。阅读以下对话片段，提取其中关于用户的持久性事实。

规则：
1. 每条事实必须是独立的、原子的一句话（一条只包含一个信息点）
2. 只提取持久性信息：身份、偏好、习惯、目标、约束条件
3. 忽略临时性内容：情绪状态、单次任务细节、寒暄
4. 如果没有值得记录的内容，输出空数组
5. 只输出 JSON，不要任何解释性文字

对话片段：
{chunk}

输出格式：
[
  {"content": "用户是软件工程师", "category": "identity"},
  {"content": "用户偏好简洁的代码注释", "category": "preference"}
]"""


# ═══════════════════════════════════════════════════════════════════
# Decision prompt
# ═══════════════════════════════════════════════════════════════════

DECISION_PROMPT = """以下是一条新提取的候选事实，以及库中可能相关的已有记忆。

新事实: "{content}" (类别: {category})

已有相关记忆:
{similar_formatted}

请判断应该执行的操作：
- ADD: 新事实独立成立，与已有记忆不冲突，新增一条
- UPDATE: 新事实是对某条已有记忆的更新/修正，标注要更新哪条（target_id）
- DELETE: 新事实使某条已有记忆过时/不再成立，标注废弃哪条（target_id）
- NONE: 新事实与已有记忆重复，无需任何操作

只输出JSON: {"action": "ADD|UPDATE|DELETE|NONE", "target_id": 数字或null, "reason": "一句话说明原因"}"""


# ═══════════════════════════════════════════════════════════════════
# MemoryStore
# ═══════════════════════════════════════════════════════════════════

class MemoryStore:
    """原子记忆存储 + BM25 + 字符 n-gram 检索。

    与 ConversationMemory 共用同一个 db 文件，
    但操作独立的 memories 表。
    """

    def __init__(
        self,
        db_path: str,
        llm_client: Any,                # SymbixClient 实例（用于调 LLM）
        extraction_model: str = "gpt-4o-mini",
        default_user_id: str = "default",
    ):
        self.db_path = db_path
        self.llm_client = llm_client
        # 仅作最后兜底：正常情况下 _resolve_model 会跟随用户当前选的模型
        self.model = extraction_model or ""
        self.default_user_id = default_user_id

        self._stop_words = _STOP_WORDS.copy()
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = Lock()

        # BM25 索引缓存：{user_id: (corpus_tokens, bm25, ids, contents, categories)}
        self._bm25_cache: dict[str, tuple] = {}

    def _resolve_model(self, override: Optional[str] = None) -> str:
        """决定后台记忆链路用哪个模型。

        回退顺序：显式 override → 当前 active provider 的模型 → 构造时的兜底值。
        之前直接退回硬编码的 gpt-4o-mini，在自定义中转网关上会 503 model_not_found，
        而失败只写进控制台日志 → 记忆永远是空的。
        """
        if override:
            return override
        registry = getattr(self.llm_client, "registry", None)
        try:
            active = registry.get_active() if registry is not None else None
        except Exception:
            active = None
        return (getattr(active, "model", "") or self.model or "")

    # ═══════════════════════════════════════════════════════════════
    # 分词 / 文本预处理
    # ═══════════════════════════════════════════════════════════════

    def tokenize(self, text: str) -> list[str]:
        """jieba 分词 + 停用词过滤，返回有意义词条的列表。

        中文用 jieba 精确模式；英文/数字按单词边界切分。
        过滤单字符、纯标点、停用词。
        """
        if not text:
            return []

        tokens: list[str] = []

        # 中文分词
        chinese_chars = re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf]+', text)
        for chunk in chinese_chars:
            tokens.extend(jieba.lcut(chunk, cut_all=False))

        # 英文/数字分词
        non_chinese = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf]+', ' ', text)
        eng_tokens = re.findall(r'[a-zA-Z0-9_]+', non_chinese)
        tokens.extend(t.lower() for t in eng_tokens if len(t) >= 2)

        # 停用词过滤 + 短词过滤
        result: list[str] = []
        for t in tokens:
            stripped = t.strip().lower()
            if not stripped or len(stripped) <= 1:
                continue
            if stripped in self._stop_words:
                continue
            result.append(stripped)

        return result

    def char_ngrams(self, text: str, n: int = 2) -> set[str]:
        """字符级 n-gram 集合，不依赖分词器。

        任意文本（中英文混合）按字符滑动窗口切 n-gram。
        """
        if not text or n < 1:
            return set()

        text = text.strip()
        if len(text) < n:
            return {text}

        grams: set[str] = set()
        for i in range(len(text) - n + 1):
            gram = text[i:i + n]
            if gram.strip():
                grams.add(gram)

        return grams

    def ngram_similarity(self, a: str, b: str, n: int = 2) -> float:
        """Jaccard 相似度：|A ∩ B| / |A ∪ B|，基于字符 n-gram。

        作为 BM25 无法匹配时的兜底相似度。
        """
        if not a or not b:
            return 0.0

        set_a = self.char_ngrams(a, n)
        set_b = self.char_ngrams(b, n)

        if not set_a or not set_b:
            return 0.0

        intersection = len(set_a & set_b)
        union = len(set_a | set_b)

        return intersection / union if union > 0 else 0.0

    # ═══════════════════════════════════════════════════════════════
    # SQLite 连接管理
    # ═══════════════════════════════════════════════════════════════

    def _ensure_conn(self) -> sqlite3.Connection:
        """延迟初始化 SQLite 连接,线程安全。首次连接时创建 memories 表。"""
        if self._conn is None:
            with self._lock:
                if self._conn is None:
                    self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                    self._conn.execute("PRAGMA journal_mode=WAL")
                    self._conn.execute("PRAGMA foreign_keys=ON")
                    # memories 表(长期记忆)。之前只连库不建表,
                    # run_pipeline INSERT 会直接 no such table → 补上。
                    self._conn.execute("""
                        CREATE TABLE IF NOT EXISTS memories (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id TEXT NOT NULL DEFAULT 'default',
                            content TEXT NOT NULL,
                            category TEXT NOT NULL DEFAULT 'other',
                            tokens TEXT NOT NULL DEFAULT '',
                            status TEXT NOT NULL DEFAULT 'active',
                            superseded_by INTEGER,
                            source_session_id TEXT,
                            confidence REAL DEFAULT 1.0,
                            access_count INTEGER NOT NULL DEFAULT 0,
                            created_at TEXT NOT NULL,
                            updated_at TEXT NOT NULL
                        )
                    """)
                    self._conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_mem_user_status ON memories(user_id, status)"
                    )
                    # 提取游标：记录每个会话「已提取到哪条消息」。
                    # 没有它的话，超过阈值的会话每轮都会把最近的消息重复提取一遍。
                    self._conn.execute("""
                        CREATE TABLE IF NOT EXISTS memory_cursors (
                            session_id TEXT PRIMARY KEY,
                            last_message_id INTEGER NOT NULL DEFAULT 0,
                            updated_at TEXT NOT NULL
                        )
                    """)
                    self._conn.commit()
        return self._conn

    # ══════════════════════════════════════════════════════════════
    # 提取游标（增量提取）
    # ══════════════════════════════════════════════════════════════

    def get_extraction_cursor(self, session_id: str) -> int:
        """返回该会话已提取到的消息 id（无记录则为 0）。"""
        try:
            conn = self._ensure_conn()
            row = conn.execute(
                "SELECT last_message_id FROM memory_cursors WHERE session_id=?",
                (session_id,),
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
            print(f"[MemoryStore] 读提取游标失败: {e}")
            return 0

    def set_extraction_cursor(self, session_id: str, last_message_id: int) -> None:
        """记录该会话已提取到的消息 id（提取成功后调用）。"""
        try:
            conn = self._ensure_conn()
            conn.execute(
                """INSERT INTO memory_cursors (session_id, last_message_id, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET
                     last_message_id=excluded.last_message_id,
                     updated_at=excluded.updated_at""",
                (session_id, int(last_message_id), datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except Exception as e:
            print(f"[MemoryStore] 写提取游标失败: {e}")

    # ═══════════════════════════════════════════════════════════════
    # BM25 索引构建 & 检索
    # ═══════════════════════════════════════════════════════════════

    def _build_bm25_index(self, user_id: str) -> tuple:
        """构建/重建 BM25 内存索引。

        返回 (bm25, ids, contents, categories)，同时缓存到 self._bm25_cache。
        索引为空的场景也缓存（空 corpus），避免反复查询 SQLite。
        """
        conn = self._ensure_conn()
        rows = conn.execute(
            """SELECT id, content, category, tokens
               FROM memories
               WHERE status = 'active' AND user_id = ?""",
            (user_id,),
        ).fetchall()

        ids: list[int] = []
        contents: list[str] = []
        categories: list[str] = []
        corpus: list[list[str]] = []

        for row in rows:
            ids.append(row[0])
            contents.append(row[1])
            categories.append(row[2])
            # 用已缓存的 tokens 列（空格分隔）
            raw_tokens = row[3]
            if raw_tokens:
                corpus.append(raw_tokens.split(" "))
            else:
                # 兜底：现场分词（极少数情况）
                corpus.append(self.tokenize(row[1]))

        if corpus:
            bm25 = BM25Okapi(corpus)
        else:
            bm25 = None

        cached = (bm25, ids, contents, categories)
        self._bm25_cache[user_id] = cached
        return cached

    def _invalidate_bm25_cache(self, user_id: str) -> None:
        """清空指定 user_id 的 BM25 缓存，下次检索时重建。"""
        self._bm25_cache.pop(user_id, None)

    def search_similar(
        self,
        query: str,
        user_id: Optional[str] = None,
        k: int = 5,
        min_score: float = 0.15,
    ) -> list[dict]:
        """BM25 + n-gram 兜底检索，返回 [{id, content, category, score}]。

        1. 若 BM25 无索引或 corpus 为空 → 返回 []
        2. BM25 打分；若全部低于阈值 → 用 ngram_similarity 补充
        3. 取 max(BM25, n-gram) 作为最终分，过滤 < min_score，取 top-k
        """
        uid = user_id or self.default_user_id

        cached = self._bm25_cache.get(uid)
        if cached is None:
            cached = self._build_bm25_index(uid)

        bm25, ids, contents, categories = cached
        if bm25 is None or not ids:
            return []

        query_tokens = self.tokenize(query)
        if not query_tokens:
            return []

        bm25_scores = bm25.get_scores(query_tokens)   # list[float], len = len(ids)

        # 如果全部 BM25 分低于阈值，尝试 n-gram 兜底
        all_below_threshold = all(s < min_score for s in bm25_scores)

        scored: list[dict] = []
        for i, (mid, content, cat) in enumerate(zip(ids, contents, categories)):
            final_score = bm25_scores[i]
            if all_below_threshold:
                ng_score = self.ngram_similarity(query, content)
                final_score = max(final_score, ng_score)

            if final_score >= min_score:
                scored.append({
                    "id": mid,
                    "content": content,
                    "category": cat,
                    "score": round(final_score, 4),
                })

        # 降序取 top-k
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    # ═══════════════════════════════════════════════════════════════
    # 提取阶段（Extraction）
    # ═══════════════════════════════════════════════════════════════

    async def extract_facts(
        self,
        dialogue_chunk: str,
        override_model: Optional[str] = None,
        override_api_key: Optional[str] = None,
        override_api_base: Optional[str] = None
    ) -> list[dict]:
        """调 LLM 从对话片段提取原子事实。

        返回 [{"content": "...", "category": "...", "tokens": "..."}, ...]
        每条 fact 已预计算 tokens。
        """
        if not dialogue_chunk.strip():
            return []

        model = self._resolve_model(override_model)
        system_prompt = EXTRACTION_PROMPT.replace("{chunk}", dialogue_chunk)

        try:
            result = await self.llm_client.chat(
                user_input="请提取记忆事实。",
                history=[],
                override_model=model,
                override_api_key=override_api_key,
                override_api_base=override_api_base,
                system_prompt=system_prompt,
            )
            raw = result.get("content", "").strip()
            # 上游报错(坏 key / 坏 base / 超时)时 content 为空,明确记日志再返回空结果
            if not raw and result.get("error"):
                print(f"[MemoryStore] extract_facts 上游报错: {result['error']}")
                return []
        except Exception as e:
            print(f"[MemoryStore] extract_facts LLM error: {e}")
            return []

        # 解析 JSON
        facts = self._parse_json_array(raw)

        # 校验 + 预计算 tokens
        validated: list[dict] = []
        for f in facts:
            content = (f.get("content") or "").strip()
            if not content:
                continue
            cat = (f.get("category") or "").strip().lower()
            if cat not in _VALID_CATEGORIES:
                cat = "other"

            tokens_str = " ".join(self.tokenize(content))

            validated.append({
                "content": content,
                "category": cat,
                "tokens": tokens_str,
            })

        return validated

    def _parse_json_array(self, raw: str) -> list[dict]:
        """尽力从 LLM 原始返回中解析 JSON 数组。"""
        if not raw:
            return []

        # 移除 markdown ```json ... ``` 外壳
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
        cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
            elif isinstance(parsed, dict):
                return [parsed]
            else:
                return []
        except json.JSONDecodeError:
            # 尝试从文本中提取 JSON 数组片段
            match = re.search(r'\[.*\]', cleaned, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, list):
                        return [item for item in parsed if isinstance(item, dict)]
                except json.JSONDecodeError:
                    pass
            return []

    # ═══════════════════════════════════════════════════════════════
    # 决策阶段（Update Logic）
    # ═══════════════════════════════════════════════════════════════

    async def decide_action(
        self,
        candidate: dict,
        user_id: Optional[str] = None,
        override_model: Optional[str] = None,
        override_api_key: Optional[str] = None,
        override_api_base: Optional[str] = None,
    ) -> dict:
        """调 LLM 判断对新提取事实应采取的操作（ADD/UPDATE/DELETE/NONE）。

        candidate = {"content": "...", "category": "..."}
        返回 {"action": "ADD|UPDATE|DELETE|NONE", "target_id": int|null, "reason": "..."}
        """
        uid = user_id or self.default_user_id
        content = candidate.get("content", "")
        category = candidate.get("category", "")

        # 检索已有相似记忆
        similar = self.search_similar(content, user_id=uid, k=3, min_score=0.15)

        if not similar:
            # 库中无相似记忆 → 直接 ADD，省一次 LLM 调用
            return {"action": "ADD", "target_id": None, "reason": "暂无相似记忆"}

        # 格式化已有记忆
        formatted = ""
        for m in similar:
            formatted += f"\n- [id={m['id']}] \"{m['content']}\" (匹配分: {m['score']})"

        prompt = (
            DECISION_PROMPT
            .replace("{content}", content)
            .replace("{category}", category)
            .replace("{similar_formatted}", formatted)
        )

        model = self._resolve_model(override_model)

        try:
            result = await self.llm_client.chat(
                user_input="请判断记忆操作。",
                history=[],
                override_model=model,
                override_api_key=override_api_key,
                override_api_base=override_api_base,
                system_prompt=prompt,
            )
            raw = result.get("content", "").strip()
            # 上游报错时别把失败当成「返回值不是 JSON」:如实写入 reason
            if not raw and result.get("error"):
                print(f"[MemoryStore] decide_action 上游报错: {result['error']}")
                return {"action": "ADD", "target_id": None, "reason": f"LLM调用失败: {result['error']}"}
        except Exception as e:
            print(f"[MemoryStore] decide_action LLM error: {e}")
            return {"action": "ADD", "target_id": None, "reason": f"LLM调用失败: {e}"}

        # 解析 JSON
        try:
            cleaned = re.sub(r'^```(?:json)?\s*', '', raw)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"action": "ADD", "target_id": None, "reason": "LLM返回非JSON,默认新增"}

        action = (parsed.get("action") or "ADD").upper()
        if action not in ("ADD", "UPDATE", "DELETE", "NONE"):
            action = "ADD"

        target_id = parsed.get("target_id")
        if target_id is not None:
            try:
                target_id = int(target_id)
            except (ValueError, TypeError):
                target_id = None

        return {
            "action": action,
            "target_id": target_id,
            "reason": parsed.get("reason", ""),
        }

    # ═══════════════════════════════════════════════════════════════
    # 写入（Apply Decision）
    # ═══════════════════════════════════════════════════════════════

    def apply_decision(
        self,
        action_result: dict,
        fact: dict,
        source_session_id: str = "",
        user_id: Optional[str] = None,
    ) -> Optional[int]:
        """执行 ADD/UPDATE/DELETE/NONE，返回新增记录的 id（ADD/UPDATE时）或 None。"""
        uid = user_id or self.default_user_id
        action = (action_result.get("action") or "ADD").upper()
        target_id = action_result.get("target_id")
        now = datetime.now(timezone.utc).isoformat()

        conn = self._ensure_conn()
        content = fact["content"]
        category = fact.get("category", "other")
        tokens = fact.get("tokens", " ".join(self.tokenize(content)))

        new_id = None

        if action == "ADD":
            cur = conn.execute(
                """INSERT INTO memories (user_id, content, category, tokens, status,
                   source_session_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
                (uid, content, category, tokens, source_session_id, now, now),
            )
            new_id = cur.lastrowid

        elif action == "UPDATE":
            # 1) 插入新记忆
            cur = conn.execute(
                """INSERT INTO memories (user_id, content, category, tokens, status,
                   source_session_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'active', ?, ?, ?)""",
                (uid, content, category, tokens, source_session_id, now, now),
            )
            new_id = cur.lastrowid
            # 2) 标记旧记忆 superseded（如果 target_id 合法）
            if target_id is not None and new_id is not None:
                conn.execute(
                    """UPDATE memories SET status='superseded', superseded_by=?, updated_at=?
                       WHERE id=? AND user_id=?""",
                    (new_id, now, target_id, uid),
                )
            else:
                # target_id 无效 → 退化为 ADD
                pass

        elif action == "DELETE":
            if target_id is not None:
                conn.execute(
                    """UPDATE memories SET status='deleted', updated_at=?
                       WHERE id=? AND user_id=?""",
                    (now, target_id, uid),
                )

        elif action == "NONE":
            pass

        conn.commit()
        self._invalidate_bm25_cache(uid)

        return new_id

    # ═══════════════════════════════════════════════════════════════
    # 读取阶段（RAG 注入对话）
    # ═══════════════════════════════════════════════════════════════

    def retrieve_for_chat(
        self,
        user_query: str,
        user_id: Optional[str] = None,
        k: int = 5,
        min_score: float = 0.15,
    ) -> str:
        """根据用户当前查询，检索相关长期记忆，返回格式化文本。

        返回空字符串表示无匹配记忆。
        """
        uid = user_id or self.default_user_id
        results = self.search_similar(user_query, user_id=uid, k=k, min_score=min_score)

        if not results:
            return ""

        # 按 category 添加中文标签
        CAT_LABELS: dict[str, str] = {
            "identity": "身份",
            "preference": "偏好",
            "habit": "习惯",
            "goal": "目标/计划",
            "constraint": "约束条件",
            "other": "其他",
        }

        lines = ["[用户长期记忆]"]
        for m in results:
            cat = m.get("category", "other")
            label = CAT_LABELS.get(cat, "其他")
            lines.append(f"- ({label}) {m['content']}")

        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════
    # 全流程入口
    # ═══════════════════════════════════════════════════════════════

    async def run_pipeline(
        self,
        dialogue_chunk: str,
        session_id: str = "",
        user_id: Optional[str] = None,
        override_model: Optional[str] = None,
        override_api_key: Optional[str] = None,
        override_api_base: Optional[str] = None,
    ) -> list[dict]:
        uid = user_id or self.default_user_id

        facts = await self.extract_facts(
            dialogue_chunk,
            override_model=override_model,
            override_api_key=override_api_key,
            override_api_base=override_api_base,
        )
        if not facts:
            return []

        applied: list[dict] = []
        for fact in facts:
            action = await self.decide_action(
                fact, user_id=uid,
                override_model=override_model,
                override_api_key=override_api_key,
                override_api_base=override_api_base,
            )
            new_id = self.apply_decision(action, fact, source_session_id=session_id, user_id=uid)
            if action["action"] in ("ADD", "UPDATE"):
                applied.append({
                    **fact,
                    "action": action["action"],
                    "new_id": new_id,
                    "target_id": action.get("target_id"),
                    "reason": action.get("reason"),
                })
        return applied

    async def remember(
        self,
        content: str,
        category: str = "other",
        source_session_id: str = "",
        user_id: Optional[str] = None,
        override_model: Optional[str] = None,
        override_api_key: Optional[str] = None,
        override_api_base: Optional[str] = None,
    ) -> dict:
        """显式保存一条记忆（工具调用路径）。

        走 decide_action/apply_decision，因此天然具备去重/更新语义：
        已有等价记忆时不重复写入，模型改口时会把旧条目标为 superseded。

        返回 {action, new_id, target_id, reason, content, category, already_known}。
        """
        uid = user_id or self.default_user_id
        text = (content or "").strip()
        fact = {
            "content": text,
            "category": category if category in _VALID_CATEGORIES else "other",
            "tokens": " ".join(self.tokenize(text)),
        }
        action = await self.decide_action(
            fact, user_id=uid,
            override_model=override_model,
            override_api_key=override_api_key,
            override_api_base=override_api_base,
        )
        new_id = self.apply_decision(action, fact, source_session_id=source_session_id, user_id=uid)
        return {
            "action": action.get("action"),
            "new_id": new_id,
            "target_id": action.get("target_id"),
            "reason": action.get("reason"),
            "content": text,
            "category": fact["category"],
            "already_known": action.get("action") == "NONE",
        }

    # ═══════════════════════════════════════════════════════════════
    # 辅助 CRUD
    # ═══════════════════════════════════════════════════════════════

    def get_active_memories(self, user_id: Optional[str] = None) -> list[dict]:
        """获取所有 active 状态记忆（调试/管理用）。"""
        uid = user_id or self.default_user_id
        conn = self._ensure_conn()
        rows = conn.execute(
            """SELECT id, content, category, tokens, status, superseded_by,
               source_session_id, confidence, access_count, created_at
               FROM memories WHERE status='active' AND user_id=?""",
            (uid,),
        ).fetchall()

        return [
            {
                "id": r[0], "content": r[1], "category": r[2], "tokens": r[3],
                "status": r[4], "superseded_by": r[5], "source_session_id": r[6],
                "confidence": r[7], "access_count": r[8], "created_at": r[9],
            }
            for r in rows
        ]

    def delete_memory(self, memory_id: int, user_id: Optional[str] = None):
        """软删除（status='deleted'）。"""
        uid = user_id or self.default_user_id
        now = datetime.now(timezone.utc).isoformat()
        conn = self._ensure_conn()
        conn.execute(
            "UPDATE memories SET status='deleted', updated_at=? WHERE id=? AND user_id=?",
            (now, memory_id, uid),
        )
        conn.commit()
        self._invalidate_bm25_cache(uid)