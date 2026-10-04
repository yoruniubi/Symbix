"""长期记忆工具 —— 让 Agent 真能「写入 / 检索」长期记忆库(memories 表)。

背景:之前系统里没有任何记忆工具,模型说「我记住了」其实只存在于本次会话上下文,
memory.db 里一行都没有;用户在手账界面自然什么也看不到。这两个工具让「记住」可兑现:

- save_memory     : 真落库(走 MemoryStore.remember → 去重/更新语义)
- search_memories : 真查库(BM25 + 字符 n-gram;query 留空则返回最近的记忆)

MemoryStore 由 main.py 启动时注入(SDK 不反向依赖 application 层),未注入时给可读错误。
"""
from __future__ import annotations

import json

from Symbix_sdk.checkpoint import get_current

# main.py lifespan 里注入(application.state.memory_store)
_store = None

# 与 MemoryStore._VALID_CATEGORIES 保持一致
_VALID_CATEGORIES = ("identity", "preference", "habit", "goal", "constraint", "other")

_MAX_CONTENT_LEN = 300


def set_memory_store(store) -> None:
    """注入 MemoryStore;重复注入时覆盖(热重载友好)。"""
    global _store
    _store = store


def _get_store():
    if _store is None:
        raise RuntimeError(
            "长期记忆库尚未就绪(后端刚启动或启动失败)。可以告诉用户稍后再试。"
        )
    return _store


def _json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _current_session_id() -> str:
    """当前会话 id(checkpoint ContextVar 透传);无上下文时返回空串。"""
    try:
        session_id, _round_id = get_current()
        return session_id or ""
    except Exception:
        return ""


async def save_memory(content: str, category: str = "other") -> str:
    """把一条关于用户的持久事实写进长期记忆库。

    已有等价记忆时不会重复写入(action=NONE);与旧记忆冲突时会把旧条目标为
    superseded(action=UPDATE)。
    """
    try:
        store = _get_store()
    except RuntimeError as e:
        return _json({"status": "error", "message": str(e)})

    text = (content or "").strip()
    if not text:
        return _json({"status": "error", "message": "content 不能为空"})
    if len(text) > _MAX_CONTENT_LEN:
        text = text[:_MAX_CONTENT_LEN]

    cat = (category or "other").strip().lower()
    if cat not in _VALID_CATEGORIES:
        cat = "other"

    try:
        result = await store.remember(
            text,
            category=cat,
            source_session_id=_current_session_id(),
        )
    except Exception as e:
        return _json({"status": "error", "message": f"写入失败:{type(e).__name__}: {e}"})

    if result.get("already_known"):
        return _json({
            "status": "ok",
            "saved": False,
            "action": "NONE",
            "message": "这条已经在长期记忆里了,没有重复保存。",
            "content": result.get("content"),
            "category": result.get("category"),
        })
    return _json({
        "status": "ok",
        "saved": True,
        "action": result.get("action"),
        "memory_id": result.get("new_id"),
        "content": result.get("content"),
        "category": result.get("category"),
        "note": "已写入长期记忆库,之后可以在聊天中被自动检索到,也会出现在手账界面。",
    })


async def search_memories(query: str = "", k: int = 5) -> str:
    """检索长期记忆库。query 留空则返回最近保存的若干条(用于「你都记得我什么」)。"""
    try:
        store = _get_store()
    except RuntimeError as e:
        return _json({"status": "error", "message": str(e)})

    try:
        limit = int(k) if k else 5
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 20))

    q = (query or "").strip()
    try:
        if q:
            hits = store.search_similar(q, k=limit)
            items = [
                {
                    "id": h.get("id"),
                    "content": h.get("content"),
                    "category": h.get("category"),
                    "score": h.get("score"),
                }
                for h in hits
            ]
        else:
            rows = store.get_active_memories()
            rows.sort(key=lambda r: (r.get("created_at") or ""), reverse=True)
            items = [
                {
                    "id": r.get("id"),
                    "content": r.get("content"),
                    "category": r.get("category"),
                    "created_at": r.get("created_at"),
                }
                for r in rows[:limit]
            ]
    except Exception as e:
        return _json({"status": "error", "message": f"检索失败:{type(e).__name__}: {e}"})

    if not items:
        return _json({
            "status": "ok",
            "count": 0,
            "memories": [],
            "message": "没有匹配的长期记忆。" + ("(库中可能还是空的)" if q else ""),
        })
    return _json({"status": "ok", "count": len(items), "query": q, "memories": items})


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

MEMORY_TOOLS_SCHEMAS = {
    "save_memory": {
        "risk_channel": "write",
        "func": save_memory,
        "description": (
            "把一条关于用户的持久事实写入**长期记忆库**(跨会话保留,会出现在手账界面)。"
            "当用户说「记住…」「以后都用…」「我叫…」「我偏好…」或者你发现值得长期记住的"
            "身份/偏好/习惯/目标/约束时调用。"
            "content 必须是一句独立、原子的陈述(一条只放一个信息点),例如「用户叫 Frank」。"
            "category 取值: identity(身份) / preference(偏好) / habit(习惯) / goal(目标) / "
            "constraint(约束) / other。"
            "注意:只有调用本工具才算真正记住;只在回复里说「记住了」等于没记。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "一句原子事实,如「用户叫 Frank」"},
                "category": {
                    "type": "string",
                    "enum": list(_VALID_CATEGORIES),
                    "description": "记忆类别,默认 other",
                },
            },
            "required": ["content"],
        },
    },
    "search_memories": {
        "risk_channel": "read",
        "func": search_memories,
        "description": (
            "检索长期记忆库。用户问「你还记得我什么」「我之前说过…吗」,或你想确认某个"
            "关于用户的事实是否已经记过时调用。query 留空则返回最近保存的若干条。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索关键词/问题;留空 = 列出最近的记忆"},
                "k": {"type": "integer", "description": "返回条数,默认 5,最多 20"},
            },
            "required": [],
        },
    },
}
