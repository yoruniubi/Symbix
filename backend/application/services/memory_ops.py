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
    EXTRACT_THRESHOLD,
    EXTRACT_MIN_NEW,
)

# 桌宠动作引导：鼓励模型在合适时机调用 emit_pet_action
PET_ACTION_HINT = (
    "【桌宠表现】你是带桌面宠物的助手。在合适时机请调用工具 emit_pet_action 驱动主窗口动画，"
    "不要只在文字里描述动作。\n"
    "常用映射：打招呼/欢迎→waving；开心/完成任务→jumping 或 happy；思考/分析→review 或 thinking；"
    "失败/抱歉→failed 或 sad；等待用户→waiting；恢复常态→idle。\n"
    "可选参数 bubble 为短中文气泡（≤40字）。同一轮回复最多调用 1–2 次，避免刷屏。"
)


def build_system_prompt_parts(
    base: str = "",
    use_memory: bool = True,
    user_query: str = "",
    session_id: str = "",
) -> tuple[str, str]:
    """同 build_system_prompt,但把结果拆成 (稳定部分, 当轮变化部分)。

    上游 prompt cache 按前缀 token 匹配:只要 system 里混进「每轮不同」的内容
    (如按用户提问做 BM25 检索回来的长期记忆),整个前缀缓存就失效。
    因此调用方应把 stable 放 system、dynamic 拼到当轮用户消息前面。

    Returns:
        (stable, dynamic) —— dynamic 可能为空字符串
    """
    stable_parts: list[str] = []
    if base and base.strip():
        stable_parts.append(base.strip())
    stable_parts.append(PET_ACTION_HINT)

    dynamic = ""
    if use_memory:
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

        if memory_text:
            dynamic = memory_text.strip()

    return "\n\n".join(stable_parts), dynamic


def build_system_prompt(
    base: str = "",
    use_memory: bool = True,
    user_query: str = "",
    session_id: str = "",
) -> str:
    """把用户长期记忆（RAG 检索自 memories 表）拼进 system_prompt，并附带桌宠动作提示。

    优先走 MemoryStore BM25 检索；若结果为空则回退到旧 user_profile 管线。
    需要前缀稳定(流式聊天链路)时改用 build_system_prompt_parts。
    """
    stable, dynamic = build_system_prompt_parts(
        base=base, use_memory=use_memory, user_query=user_query, session_id=session_id,
    )
    return f"{stable}\n\n{dynamic}" if dynamic else stable



# ═══════════════════════════════════════════════════════════════════
# maybe_extract_memories  —— 新记忆提取管线（替代 maybe_extract_profile）
# ═══════════════════════════════════════════════════════════════════

async def maybe_extract_memories(
    session_id: str,
    api_key: str = "",
    api_base: str = "",
    model: str = "",
):
    """把会话里值得长期记住的事实提取进 memories 表。

    两个坑点（之前导致「模型说记住了、手账里却什么都没有」）：
    1. 门槛高 + 无游标：会话消息数不到 16 就永不提取，到了又每轮重复提取最近一段。
       现在改成 EXTRACT_THRESHOLD(6) 起步 + memory_cursors 增量提取。
    2. 读历史不在 try 里：库有问题（如索引损坏）时直接抛给 create_task，
       异常被默默吞掉，外面完全看不出来。现在读/写都包住并打日志。
    """
    try:
        total = memory.count_messages(session_id)
        if total < EXTRACT_THRESHOLD:
            return
        all_msgs = memory.get_history_with_ids(session_id, limit=total)
    except Exception as e:
        print(f"[Memory] 读取会话历史失败,跳过记忆提取 (session={session_id[:8]}…): {e}")
        return

    if not all_msgs:
        return

    cursor = memory_store.get_extraction_cursor(session_id)
    new_msgs = [m for m in all_msgs if m.get("id", 0) > cursor]
    if len(new_msgs) < EXTRACT_MIN_NEW:
        return

    # 取最近的一批（新消息 + 少量上下文），避免一次丢太多进去
    window = new_msgs[-EXTRACT_THRESHOLD:]
    chunk_lines: list[str] = []
    for m in window:
        role = m.get("role", "user")
        content = (m.get("content") or "")[:500]
        chunk_lines.append(f"{role}: {content}")
    dialogue_chunk = "\n".join(chunk_lines)

    try:
        applied = await memory_store.run_pipeline(
            dialogue_chunk=dialogue_chunk,
            session_id=session_id,
            override_model=model or None,
            override_api_key=api_key or None,
            override_api_base=api_base or None,
        )
    except Exception as e:
        # 不推进游标 —— 下一轮还会再试一次
        print(f"[Memory] extract_memories failed (session={session_id[:8]}…): {e}")
        return

    # 提取成功（含「没什么值得记的」）→ 推进游标，不重复处理同一批消息
    memory_store.set_extraction_cursor(session_id, window[-1]["id"])
    if applied:
        print(f"[Memory] Extracted {len(applied)} new/updated facts from session {session_id[:8]}…")
        for f in applied:
            print(f"  - [{f.get('action')}] {f.get('content')}")


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
    try:
        total = memory.count_messages(session_id)
    except Exception as e:
        print(f"[Memory] 统计消息数失败,跳过压缩 (session={session_id[:8]}…): {e}")
        return
    if total < COMPRESS_THRESHOLD:
        return

    existing = memory.get_summary(session_id)
    covered = existing["covered_until_id"] if existing else 0

    try:
        all_msgs = memory.get_history_with_ids(session_id, limit=total)
    except Exception as e:
        print(f"[Memory] 读取会话历史失败,跳过压缩 (session={session_id[:8]}…): {e}")
        return
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
        elif result.get("error"):
            # 上游失败时不要静默:明确记录,下次触发会重试
            print(f"[Memory] Compress skipped (上游报错): {result['error']}")
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