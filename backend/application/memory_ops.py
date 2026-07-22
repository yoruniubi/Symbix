"""上下文压缩 & 用户画像相关后台任务。"""
import json as _json

from application.state import (
    memory,
    symbix_client,
    skill_registry,
    COMPRESS_THRESHOLD,
    RECENT_KEEP,
)


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


async def maybe_extract_profile(
    session_id: str,
    user_msg: str,
    assistant_msg: str = "",
    api_key: str = "",
    api_base: str = "",
    model: str = "",
):
    """从本轮对话中提取用户画像事实，写入 user_profile"""
    if len(user_msg) < 20:
        return

    existing = memory.get_profile()
    existing_text = (
        "\n".join(f"- {k}: {v}" for k, v in existing.items()) if existing else "（暂无）"
    )

    prompt = (
        "从以下对话中提取关于用户的长期事实（职业、公司、项目、技术栈、偏好、目标等）。\n"
        "只输出 JSON 对象，key 为中文短标签，value 为简短描述。\n"
        "如果没有新的可提取事实，返回空对象 {}。\n"
        "不要编造，不要输出 JSON 以外的内容。\n\n"
        f"【已有画像】\n{existing_text}\n\n"
        f"【用户】{user_msg[:500]}\n"
        f"【助手】{(assistant_msg or '')[:300]}"
    )
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
        raw = (result.get("content") or "").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            facts = _json.loads(raw[start : end + 1])
            if isinstance(facts, dict) and facts:
                clean = {str(k): str(v) for k, v in facts.items() if k and v}
                if clean:
                    memory.set_profile_facts(clean)
                    print(f"[Memory] Profile updated: {list(clean.keys())}")
    except Exception as e:
        print(f"[Memory] Profile extract failed: {e}")


def build_system_prompt(base: str = "") -> str:
    """把用户画像拼进 system_prompt"""
    profile_text = memory.get_profile_prompt()
    if not profile_text:
        return base or ""
    if base:
        return f"{base}\n\n{profile_text}"
    return profile_text


def format_sse(event: dict) -> str:
    """把事件 dict 转成 SSE 文本"""
    event_type = event.get("type", "message")
    payload = _json.dumps(event, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"
