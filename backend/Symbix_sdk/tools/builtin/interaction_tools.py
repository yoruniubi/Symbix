from __future__ import annotations
import json
import uuid


def ask_clarifying_question(
    question: str,
    suggestions: list[str] | None = None,
    context: str = "",
) -> str:
    """向用户提出澄清问题，暂停当前任务等待用户回答。

    Args:
        question: 需要向用户确认的具体问题
        suggestions: 可选，2-4 个建议答案，便于用户快速选择
        context: 可选，简要说明为什么需要澄清

    Returns:
        JSON 字符串，包含待处理的问题信息；主循环需识别本工具并挂起等待用户输入
    """
    question = (question or "").strip()
    if not question:
        return json.dumps(
            {"status": "error", "message": "question 不能为空"},
            ensure_ascii=False,
        )

    suggestions = [s.strip() for s in (suggestions or []) if s and s.strip()]
    request_id = uuid.uuid4().hex[:8]

    try:
        # 与 emit_pet_action 类似：经事件总线推送到前端，
        # 让前端渲染成问答卡片/按钮（如果有 suggestions）
        from application.services.pet_action import pet_action

        pet_action.emit(
            "waiting",
            bubble=question[:40],
            source="ask_clarifying_question",
        )
    except Exception:
        pass  

    return json.dumps(
        {
            "status": "pending_user_input",
            "id": request_id,
            "question": question,
            "suggestions": suggestions,
            "context": context.strip(),
            "message": "已向用户发起提问，等待回复后再继续",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

INTERACTION_TOOLS_SCHEMAS = {
    "ask_clarifying_question": {
        "func": ask_clarifying_question,
        "description": (
            "当任务存在关键信息缺失、或存在多种互斥的合理理解方式，"
            "且继续执行可能导致方向性错误时调用，向用户主动提问澄清。"
            "不要用于无关紧要的细节确认——能合理假设的应直接假设并说明，而不是打断用户。"
            "如果问题是可枚举的选择题，通过 suggestions 提供 2-4 个候选答案，"
            "前端会渲染成可点击按钮；开放式问题可不传 suggestions。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "向用户提出的具体问题，需清晰、可直接回答",
                },
                "suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选：2-4 个建议答案/选项，供用户快速点选",
                },
                "context": {
                    "type": "string",
                    "description": "可选：简要说明为何需要澄清，帮助用户理解卡在了哪里",
                },
            },
            "required": ["question"],
        },
    },
}