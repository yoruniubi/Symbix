"""上下文压缩 & 记忆提取相关后台任务。

记忆提取走新管线 (MemoryStore)：BM25 + LLM 提取/决策，原子事实落地 memories 表。
画像规则匹配 (extract_profile_by_rules) 保留为兜底，但 build_system_prompt 已改走 RAG 检索。
上下文压缩仍可选地调用模型做摘要。
"""
from __future__ import annotations

import json as _json
from typing import Optional

from application.state import (
    memory,
    memory_store,
    symbix_client,
    skill_registry,
    COMPRESS_THRESHOLD,
    RECENT_KEEP,
)


# ═══════════════════════════════════════════════════════════════════
# build_system_prompt  —— 注入 RAG 检索结果（新）
# ═══════════════════════════════════════════════════════════════════

def build_system_prompt(
    base: str = "",
    use_memory: bool = True,
    user_query: str = "",
    session_id: str = "",
) -> str:
    """把用户长期记忆（RAG 检索自 memories 表）拼进 system_prompt。

    优先走 MemoryStore BM25 检索；若结果为空则回退到旧 user_profile 管线。
    """
    if not use_memory:
        return base or ""

    memory_text = ""

    # ── 新管线：BM25 检索 ──
    if user_query.strip():
        try:
            memory_text = memory_store.retrieve_for_chat(user_query, k=5)
        except Exception as e:
            print(f"[Memory] RAG retrieve failed: {e}")

    # ── 回退：旧画像管线 ──
    if not memory_text:
        memory_text = memory.get_profile_prompt()

    if not memory_text:
        return base or ""

    if base:
        return f"{base}\n\n{memory_text}"
    return memory_text


# ═══════════════════════════════════════════════════════════════════
# maybe_extract_memories  —— 新记忆提取管线（替代 maybe_extract_profile）
# ═══════════════════════════════════════════════════════════════════

async def maybe_extract_memories(
    session_id: str,
    api_key: str = "",
    api_base: str = "",
    model: str = "",
):
    """压缩阈值触发后，取最近 COMPRESS_THRESHOLD 条消息，
    异步调 MemoryStore.run_pipeline 提取原子记忆。

    异常时不抛，仅打日志。
    """
    total = memory.count_messages(session_id)
    if total < COMPRESS_THRESHOLD:
        return

    all_msgs = memory.get_history_with_ids(session_id, limit=total)
    if len(all_msgs) < COMPRESS_THRESHOLD:
        return

    # 取最近 COMPRESS_THRESHOLD 条拼成 dialogue chunk
    recent = all_msgs[-COMPRESS_THRESHOLD:]
    chunk_lines: list[str] = []
    for m in recent:
        role = m.get("role", "user")
        content = (m.get("content") or "")[:500]
        chunk_lines.append(f"{role}: {content}")
    dialogue_chunk = "\n".join(chunk_lines)

    try:
        applied = await memory_store.run_pipeline(
            dialogue_chunk=dialogue_chunk,
            session_id=session_id,
        )
        if applied:
            print(f"[Memory] Extracted {len(applied)} new/updated facts from session {session_id[:8]}…")
            for f in applied:
                print(f"  - [{f.get('action')}] {f.get('content')}")
    except Exception as e:
        print(f"[Memory] extract_memories failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# maybe_compress_session  —— 上下文压缩（不变）
# ═══════════════════════════════════════════════════════════════════

async def maybe_compress_session(
    session_id: str,
    api_key: str = "",
    api_base: str = "",
    model: str = "",
):
    """若消息数超过阈值，对旧消息做阶段性摘要并写入 session_summaries"""
    total = memory.count_messages(session_id)
    if total < COMPRESS_THRESHOLD:
        return

    existing = memory.get_summary(session_id)
    covered = existing["covered_until_id"] if existing else 0

    all_msgs = memory.get_history_with_ids(session_id, limit=total)
    if len(all_msgs) <= RECENT_KEEP:
        return

    old_msgs = [m for m in all_msgs[:-RECENT_KEEP] if m["id"] > covered]
    if len(old_msgs) < 4:
        return

    dialogue = "\n".join(
        f"{m['role']}: {m['content'][:300]}" for m in old_msgs
    )
    prev_summary = existing["summary"] if existing else ""
    prompt = (
        "请将以下对话内容压缩为简洁的中文摘要（200字以内），"
        "保留关键事实、结论、用户意图与未完成事项。"
        "只输出摘要正文，不要标题或解释。\n\n"
    )
    if prev_summary:
        prompt += f"【已有摘要】\n{prev_summary}\n\n"
    prompt += f"【需压缩的新对话】\n{dialogue}"

    try:
        result = await symbix_client.chat(
            user_input=prompt,
            history=[],
            registry=skill_registry,
            tools=None,
            override_api_key=api_key or None,
            override_api_base=api_base or None,
            override_model=model or None,
        )
        summary = (result.get("content") or "").strip()
        if summary:
            covered_until = old_msgs[-1]["id"]
            memory.set_summary(session_id, summary, covered_until)
            print(f"[Memory] Compressed session {session_id[:8]}… until id={covered_until}")
    except Exception as e:
        print(f"[Memory] Compress failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# 旧画像管线（保留兜底，但不再自动调用）
# ═══════════════════════════════════════════════════════════════════

# ─── 规则词表（保留不动）─────────────────────────────────────

import re

_JOB_KEYWORDS: list[tuple[str, str]] = [
    ("全栈工程师", "全栈工程师"),
    ("全栈开发", "全栈工程师"),
    ("前端工程师", "前端工程师"),
    ("前端开发", "前端工程师"),
    ("后端工程师", "后端工程师"),
    ("后端开发", "后端工程师"),
    ("算法工程师", "算法工程师"),
    ("数据工程师", "数据工程师"),
    ("数据科学家", "数据科学家"),
    ("机器学习", "机器学习工程师"),
    ("产品经理", "产品经理"),
    ("项目经理", "项目经理"),
    ("UI 设计师", "UI 设计师"),
    ("UI设计师", "UI 设计师"),
    ("UX 设计师", "UX 设计师"),
    ("UX设计师", "UX 设计师"),
    ("设计师", "设计师"),
    ("程序员", "程序员"),
    ("软件工程师", "软件工程师"),
    ("开发者", "开发者"),
    ("工程师", "工程师"),
    ("运维", "运维工程师"),
    ("测试工程师", "测试工程师"),
    ("QA", "测试工程师"),
    ("老师", "老师"),
    ("教师", "教师"),
    ("学生", "学生"),
    ("研究生", "研究生"),
    ("博士", "博士"),
    ("创业者", "创业者"),
    ("自由职业", "自由职业"),
    ("自由职业者", "自由职业"),
]

_TECH_KEYWORDS: list[str] = [
    "TypeScript", "JavaScript", "Python", "Rust", "Go", "Golang",
    "Java", "Kotlin", "Swift", "C++", "C#", "PHP", "Ruby", "Scala",
    "Vue", "React", "Angular", "Svelte", "Next.js", "Nuxt",
    "Node.js", "Deno", "Django", "FastAPI", "Flask", "Spring",
    "Tauri", "Electron", "Docker", "Kubernetes", "K8s",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "SQLite",
    "AWS", "Azure", "GCP", "Linux", "Git",
    "PyTorch", "TensorFlow", "LangChain", "OpenAI",
    "Tailwind", "Naive UI", "Element Plus",
]

_PREF_PATTERNS = [
    re.compile(r"(?:我喜欢|偏好|习惯于?|更倾向)(.{2,40}?)(?:[。！？\n]|$)"),
    re.compile(r"(?:请用|希望你用|回答时用)(.{2,30}?)(?:[。！？\n]|$)"),
]

_COMPANY_PATTERNS = [
    re.compile(r"(?:我在|就职于|任职于|供职于)([^\s，,。！？\n]{2,30}?)(?:工作|上班|任职)?"),
    re.compile(r"(?:公司是|公司叫|所在公司[是为])([^\s，,。！？\n]{2,30})"),
]

_NAME_PATTERNS = [
    re.compile(r"(?:我叫|叫我|我的名字是|名字是)([A-Za-z\u4e00-\u9fff·]{1,20})"),
]

_PROJECT_PATTERNS = [
    re.compile(r"(?:我在做|正在做|在开发|在写|项目是|项目叫)([^\s，,。！？\n]{2,40})"),
]


def _match_job(text: str) -> Optional[str]:
    m = re.search(
        r"(?:我是一名?|我是个|我做|我的职业是|职业是|从事|我在做)(.{1,20}?)(?:[，,。！？\n]|$)",
        text,
    )
    if m:
        candidate = m.group(1).strip()
        for kw, label in _JOB_KEYWORDS:
            if kw.lower() in candidate.lower() or kw in candidate:
                return label
        if 1 < len(candidate) <= 12 and not re.search(r"[的了吗呢吧啊]", candidate):
            return candidate

    lower = text.lower()
    for kw, label in _JOB_KEYWORDS:
        if kw.lower() in lower or kw in text:
            if re.search(rf"(?:不是|并非|别当)[^\n]{{0,6}}{re.escape(kw)}", text):
                continue
            return label
    return None


def _match_techs(text: str) -> list[str]:
    found: list[str] = []
    for tech in sorted(_TECH_KEYWORDS, key=len, reverse=True):
        if re.search(r"[A-Za-z]", tech):
            pattern = re.compile(rf"(?<![A-Za-z0-9_+.#]){re.escape(tech)}(?![A-Za-z0-9_+])", re.I)
            if pattern.search(text):
                if tech not in found:
                    found.append(tech)
        else:
            if tech in text and tech not in found:
                found.append(tech)
    return found[:12]


def _first_group(patterns: list[re.Pattern], text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            val = (m.group(1) or "").strip()
            if val:
                return val
    return None


def extract_profile_by_rules(user_msg: str) -> dict[str, str]:
    """用关键词/正则从用户消息中提取画像事实（旧管线，已降级为兜底）。

    返回 {中文标签: 值}，无匹配时返回空 dict。
    """
    if not user_msg or not user_msg.strip():
        return {}

    text = user_msg.strip()
    facts: dict[str, str] = {}

    job = _match_job(text)
    if job:
        facts["职业"] = job

    techs = _match_techs(text)
    if techs:
        facts["技术栈"] = "、".join(techs)

    company = _first_group(_COMPANY_PATTERNS, text)
    if company:
        facts["公司"] = company.strip("的了着")

    name = _first_group(_NAME_PATTERNS, text)
    if name:
        facts["称呼"] = name.strip()

    project = _first_group(_PROJECT_PATTERNS, text)
    if project:
        facts["当前项目"] = project.strip("的了着")

    pref = _first_group(_PREF_PATTERNS, text)
    if pref:
        facts["偏好"] = pref.strip("，,。 ")

    return facts


def pick_profile_from_history(session_id: str, user_msg: str) -> dict[str, str]:
    """旧画像提取入口（保留兼容，不再被 chat.py 自动调用）。"""
    facts = extract_profile_by_rules(user_msg)
    if facts:
        memory.set_profile_facts(facts)
        print(f"[Memory] Profile (rules/short): {facts}")
    return facts


async def maybe_extract_profile(
    session_id: str,
    user_msg: str,
    assistant_msg: str = "",
    api_key: str = "",
    api_base: str = "",
    model: str = "",
):
    """旧画像提取入口（保留兼容，不再被 chat.py 自动调用）。"""
    _ = (session_id, assistant_msg, api_key, api_base, model)
    text = (user_msg or "").strip()
    if not text:
        return
    facts = extract_profile_by_rules(text)
    if not facts:
        return
    existing = memory.get_profile()
    to_write: dict[str, str] = {}
    for k, v in facts.items():
        if not v:
            continue
        if k == "技术栈" and existing.get(k):
            old_set = {x.strip() for x in existing[k].replace(",", "、").split("、") if x.strip()}
            new_set = {x.strip() for x in v.replace(",", "、").split("、") if x.strip()}
            merged = "、".join(sorted(old_set | new_set, key=lambda x: x.lower()))
            if merged != existing[k]:
                to_write[k] = merged
        elif existing.get(k) != v:
            to_write[k] = v
    if to_write:
        memory.set_profile_facts(to_write)
        print(f"[Memory] Profile updated: {to_write}")


# ═══════════════════════════════════════════════════════════════════
# SSE 格式化（不变）
# ═══════════════════════════════════════════════════════════════════

def format_sse(event: dict) -> str:
    """把事件 dict 转成 SSE 文本"""
    event_type = event.get("type", "message")
    payload = _json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"