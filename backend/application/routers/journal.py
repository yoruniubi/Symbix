from __future__ import annotations
import os.path as osp
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query
from application.state import memory_store

_DB_PATH = osp.join(
    osp.dirname(osp.abspath(__file__)),
    "..", "..", "Symbix_sdk", "memory", "memory.db",
)

router = APIRouter(tags=["journal"])


def _utc_range_for_local_date(date_str: str) -> tuple[str, str]:
    """本地日期 → UTC 时间区间（左闭右开），用于查 memories.created_at。"""
    local_start = datetime.strptime(date_str, "%Y-%m-%d")
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc).isoformat(),
        local_end.astimezone(timezone.utc).isoformat(),
    )

# AI 小巧思:针对每条记忆配一句俏皮感想
_THOUGHTS = [
    "这条我帮你记着啦~",
    "嗯,这很重要,不会忘的。",
    "我悄悄放进了我的小本本📒",
    "记住了!下次会主动想起来的~",
    "这条像颗小种子,我已经种下啦。",
    "放心,我记得牢牢的~",
    "好嘞,记进心里了。",
    "这让我更了解你一点点了~",
    "以后会用到这条的,我先存好~",
    "这条我记住啦，像把小纸条塞进幸运饼干里🥠",  
    "嗯，已经收进我的小脑袋瓜，稳稳的。",  
    "记下了！下次它会自己蹦出来找你。",  
    "这条我给它系了根小绳子，不怕丢~ ", 
    "好，我悄悄写进“不能忘”那一页。",   
    "收到，我把它养成一只会提醒你的小信鸽🕊️",  
    "这条我记住咯，还给它留了个小座位。",   
    "嗯嗯，已经存好，像藏了一颗小糖果🍬",  
    "放心，这条我会记得比闹钟还准。",  
    "记下啦，下次见面它就变成“我还记得哦~"
]

_CATEGORY_LABEL = {
    "identity": "身份",
    "preference": "偏好",
    "habit": "习惯",
    "goal": "目标",
    "constraint": "约束",
    "other": "其他",
}


@router.get("/journal/daily")
async def journal_daily(
    date: str = Query(..., description="YYYY-MM-DD,如 2026-09-01"),
):
    """某一天的手账:当天新增记忆 + AI 小巧思。"""
    try:
        from datetime import datetime
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date 格式应为 YYYY-MM-DD")

    # ── 当天新增记忆(memories 表)──────────────────────────
    mem_rows = []
    try:
        start_utc, end_utc = _utc_range_for_local_date(date)
        conn = memory_store._ensure_conn()
        rows = conn.execute(
            """SELECT id, content, category, status, created_at
               FROM memories
               WHERE created_at >= ? AND created_at < ? AND status='active'
               ORDER BY created_at DESC
               LIMIT 30""",
            (start_utc, end_utc),
        ).fetchall()
        for r in rows:
            mem_rows.append({
                "id": r[0],
                "content": r[1],
                "category": r[2],
                "category_label": _CATEGORY_LABEL.get(r[2], r[2]),
                "status": r[3],
                "created_at": r[4],
            })
    except Exception as e:
        print(f"[journal] memories query failed: {e}")

    # ── 当天统计(消息数 / 记忆数)────────────────────────
    msg_count = 0
    mem_count = len(mem_rows)
    try:
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        row = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE created_at LIKE ?",
            (date + "%",),
        ).fetchone()
        msg_count = row[0] if row else 0
        conn.close()
    except Exception as e:
        print(f"[journal] messages count failed: {e}")

    # ── AI 小巧思:为每条记忆配一句感想 ────────────────────
    tips = [
        {
            "content": m["content"],
            "thought": random.choice(_THOUGHTS),
            "category_label": m["category_label"],
        }
        for m in mem_rows[:6]
    ]

    return {
        "date": date,
        "stats": {"message_count": msg_count, "memory_count": mem_count},
        "memories": mem_rows,
        "ai_tips": tips,
    }

# ═══════════════════════════════════════════════════════════════════
# 记忆库（搜索 + 分类汇总）
#
# 手账页原来只能按天翻，用户想「找一条我记得过的某件事」时无从下手。
# 这里把整个 memories 表摊开：既能按关键词搜，也能按「约束 / 个人信息 /
# 项目记忆 / 其他」四组看总量，方便判断哪些领域记得多、哪些还空着。
# ═══════════════════════════════════════════════════════════════════

# 细分类别 → 大分组。分组的语义是给用户看的视角，不改 DB（老记忆不用迁移）：
#   constraint  项目/任务上必须遵守的约束（不要动 X、必须用 Y）
#   personal    关于用户本人（身份、偏好、习惯）
#   project     项目与目标相关的过程记忆
#   other       没归进上面三类的杂项，兜底展示，不丢数据
_CATEGORY_GROUP: dict[str, str] = {
    "constraint": "constraint",
    "identity": "personal",
    "preference": "personal",
    "habit": "personal",
    "goal": "project",
    "other": "other",
}

# 展示顺序：约束最需要被看见，杂项放最后
_GROUP_ORDER: list[str] = ["constraint", "personal", "project", "other"]

_GROUP_LABEL: dict[str, str] = {
    "constraint": "约束",
    "personal": "个人信息",
    "project": "项目记忆",
    "other": "其他",
}

_VALID_CATEGORY_KEYS: set[str] = set(_CATEGORY_LABEL.keys())


def _escape_like(text: str) -> str:
    """把用户输入转成安全的 LIKE 模式（转义 % _ \\，防止通配符炸全表）。"""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _categories_for(
    category: str = "",
    group: str = "",
) -> list[str]:
    """把 category / group 两种筛选方式归一成细分类别列表（空列表 = 不筛）。"""
    picked = [c for c in (category or "").split(",") if c.strip() in _VALID_CATEGORY_KEYS]
    picked = [c.strip() for c in picked]
    if group and group in _GROUP_ORDER:
        grouped = [c for c in _VALID_CATEGORY_KEYS if _CATEGORY_GROUP.get(c) == group]
        # 同时给了 category 和 group 时取交集，避免两个条件互相打架
        picked = [c for c in picked if c in grouped] if picked else grouped
    return picked


def _row_to_item(
    row: tuple,
    score: float = 0.0,
    match: str = "",
) -> dict:
    cat = row[2]
    group_key = _CATEGORY_GROUP.get(cat, "other")
    return {
        "id": row[0],
        "content": row[1],
        "category": cat,
        "category_label": _CATEGORY_LABEL.get(cat, cat),
        "group": group_key,
        "group_label": _GROUP_LABEL.get(group_key, _GROUP_LABEL["other"]),
        "created_at": row[3],
        "source_session_id": row[4],
        "access_count": row[5],
        "score": score,
        "match": match,
    }


def _build_category_summary(uid: str) -> dict:
    """按细分类别统计 active 记忆数量，再汇总成四个大分组。"""
    counts: dict[str, int] = {}
    try:
        conn = memory_store._ensure_conn()
        for cat, cnt in conn.execute(
            "SELECT category, COUNT(*) FROM memories WHERE status='active' AND user_id=? GROUP BY category",
            (uid,),
        ).fetchall():
            counts[str(cat)] = int(cnt)
    except Exception as e:  # 库还没建表 / 被锁 → 汇总给空，页面仍可用
        print(f"[journal] memory summary failed: {e}")

    groups = []
    for gkey in _GROUP_ORDER:
        cats = [
            {
                "key": ckey,
                "label": _CATEGORY_LABEL[ckey],
                "count": counts.get(ckey, 0),
            }
            for ckey in sorted(_VALID_CATEGORY_KEYS)
            if _CATEGORY_GROUP.get(ckey) == gkey
        ]
        groups.append({
            "key": gkey,
            "label": _GROUP_LABEL[gkey],
            "count": sum(c["count"] for c in cats),
            "categories": cats,
        })
    return {"groups": groups, "total": sum(counts.values())}


@router.get("/journal/memories")
async def journal_memories(
    q: str = Query("", description="搜索关键词，空则列全部"),
    category: str = Query("", description="细分类别，逗号分隔；空为全部"),
    group: str = Query("", description="大分组 constraint/personal/project/other"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """记忆库：列表 / 关键词搜索 / 分类汇总。

    搜索走两条路合并 —— 子串匹配（用户敲的关键词原样出现，最符合直觉）+
    BM25/ngram（词序不同也能找回）。两者按 id 去重，子串命中优先。
    """
    uid = memory_store.default_user_id
    keyword = (q or "").strip()
    cats = _categories_for(category, group)

    where_cat = ""
    params: list = [uid]
    if cats:
        placeholders = ",".join("?" for _ in cats)
        where_cat = f" AND category IN ({placeholders})"
        params.extend(cats)

    rows_by_id: dict[int, tuple] = {}
    scores: dict[int, tuple[float, str]] = {}

    try:
        conn = memory_store._ensure_conn()
        base_sql = (
            "SELECT id, content, category, created_at, source_session_id, access_count "
            "FROM memories WHERE status='active' AND user_id=?" + where_cat
        )
        if keyword:
            like_sql = base_sql + " AND content LIKE ? ESCAPE '\\' ORDER BY created_at DESC LIMIT 500"
            for row in conn.execute(like_sql, (*params, _escape_like(keyword))).fetchall():
                rows_by_id[row[0]] = row
                scores[row[0]] = (1.0, "literal")
        else:
            list_sql = base_sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            for row in conn.execute(list_sql, (*params, limit, offset)).fetchall():
                rows_by_id[row[0]] = row
                scores[row[0]] = (0.0, "")
    except Exception as e:
        print(f"[journal] memories query failed: {e}")
        raise HTTPException(status_code=500, detail=f"记忆库读取失败: {e}")

    literal_matched = len(rows_by_id)
    semantic_added = 0

    # 关键词搜索补一层语义召回（BM25 + 2-gram 兜底）。
    # 这里的纪律很关键：只有字面命中不足一页时才补，且最多补 20 条 ——
    # BM25 只看词面，「用户」这类高频词会把半个库都捞出来，列表一屏全是「相关」，
    # 用户反而找不到自己真要的那条。宁可少列，也不要拿噪音盖住精确命中。
    if keyword and literal_matched < limit:
        budget = min(20, limit - literal_matched)
        try:
            hits = memory_store.search_similar(keyword, uid, k=60, min_score=0.35)
            # 再按「相对最高分」砍一刀：BM25 分随语料变化，绝对阈值挡不住长尾 ——
            # 记忆库很小的时候，几十条都能过 0.35，全列出来跟没搜一样。
            top_score = float(hits[0]["score"]) if hits else 0.0
            for hit in hits:
                if semantic_added >= budget:
                    break
                if float(hit.get("score", 0.0)) < top_score * 0.5:
                    break
                mid = int(hit["id"])
                if mid in rows_by_id:
                    continue
                if cats and hit.get("category") not in cats:
                    continue
                rows_by_id[mid] = (
                    mid,
                    hit["content"],
                    hit.get("category", "other"),
                    "",  # search_similar 不返回 created_at，置空由前端隐藏
                    hit.get("source_session_id", ""),
                    0,
                )
                scores[mid] = (float(hit.get("score", 0.0)), "semantic")
                semantic_added += 1
        except Exception as e:
            print(f"[journal] memory search failed: {e}")

    items = [
        _row_to_item(row, *scores.get(row[0], (0.0, "")))
        for row in rows_by_id.values()
    ]
    if keyword:
        # 两步稳定排序：先时间新→旧，再让「字面命中」整组提到语义相关前面。
        # 单按 score 排是不行的 —— BM25 分能到 8，会把 score=1.0 的精确命中挤到后面。
        items.sort(key=lambda it: it["created_at"] or "", reverse=True)
        items.sort(key=lambda it: (0 if it["match"] == "literal" else 1, -it["score"]))
    else:
        items.sort(key=lambda it: (it["created_at"] or "", it["id"]), reverse=True)

    matched = len(items)
    page = items[offset:offset + limit] if keyword else items

    return {
        "query": keyword,
        "category": category,
        "group": group,
        "limit": limit,
        "offset": offset,
        "matched": matched,
        "literal_matched": literal_matched,
        "semantic_added": semantic_added,
        "returned": len(page),
        "summary": _build_category_summary(uid),
        "items": page,
    }
