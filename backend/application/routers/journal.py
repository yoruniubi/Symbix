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