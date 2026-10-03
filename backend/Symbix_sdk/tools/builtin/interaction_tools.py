from __future__ import annotations
import json
import re
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
# 计划确认(plan & solve 的「先提待办、等用户点头」)
# ---------------------------------------------------------------------------

PLAN_SUGGESTIONS = ["按此执行", "需要调整", "先不执行"]


def _normalize_steps(steps) -> list[str]:
    """把模型给的步骤归一化成字符串列表。

    模型可能传数组,也可能传一个带编号的多行字符串(``1. xxx\n2. yyy``),
    这里两种都收,并去掉行首的 ``1.`` / ``- `` 等编号。
    """
    if isinstance(steps, str):
        raw = [line for line in steps.splitlines()]
    elif isinstance(steps, (list, tuple, set)):
        raw = list(steps)
    else:
        raw = []

    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if not text:
            continue
        # 去掉行首编号/项目符(模型自己写编号时避免出现「1. 1. xxx」)
        text = re.sub(r"^\s*(?:\d+[.)、]|[-*•])\s*", "", text).strip()
        if text:
            out.append(text)
    return out


def propose_plan(
    steps: list[str] | str,
    question: str = "",
    notes: str = "",
) -> str:
    """把待办清单提交给用户确认，暂停任务等待用户点头后再执行。

    Args:
        steps: 待办清单，数组或带编号的多行文本（2-8 条为宜）
        question: 可选，向用户提的问题，默认「我打算按下面这几步做，可以吗？」
        notes: 可选，补充说明（关键取舍、风险、需要用户先提供的东西）

    Returns:
        JSON 字符串，主循环识别 ``status=pending_user_input`` 后挂起并渲染计划确认卡
    """
    plan = _normalize_steps(steps)
    if not plan:
        return json.dumps(
            {"status": "error", "message": "steps 不能为空,请给出 1 条以上的待办步骤"},
            ensure_ascii=False,
        )
    plan = plan[:12]
    question = (question or "").strip() or "我打算按下面这几步来做,可以吗?"
    context = (notes or "").strip()
    request_id = uuid.uuid4().hex[:8]

    try:
        from application.services.pet_action import pet_action

        pet_action.emit("waiting", bubble="计划待确认", source="propose_plan")
    except Exception:
        pass

    plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))
    return json.dumps(
        {
            "status": "pending_user_input",
            "id": request_id,
            # kind=plan 让前端渲染成「执行计划确认」卡,而不是普通提问
            "kind": "plan",
            "question": question,
            "plan": plan,
            "suggestions": list(PLAN_SUGGESTIONS),
            # 卡片正文直接显示编号清单(前端已有的 context 渲染)
            "context": plan_text if not context else f"{plan_text}\n\n{context}",
            "message": "已将待办清单提交用户确认,等待回复后再继续执行",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

INTERACTION_TOOLS_SCHEMAS = {
    "propose_plan": {
        "risk_channel": "read",
        "func": propose_plan,
        "description": (
            "把即将执行的待办清单提交给用户确认,等用户点头后再动手。"
            "当任务需要多步完成(≥3 步)、会修改多个文件/系统状态、或方案有多种取舍时,"
            "**先调用本工具**列出计划;用户可在卡片上点「按此执行」或写下修改意见。"
            "用户确认后你会收到「计划已确认」+ 清单,按顺序执行即可,不要跳过确认直接改文件。"
            "简单问答、单步操作不要调用本工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "待办步骤(2-8 条为宜),每条一句话、可执行、有先后顺序",
                },
                "question": {
                    "type": "string",
                    "description": "可选:向用户提的问题,默认「我打算按下面这几步来做,可以吗?」",
                },
                "notes": {
                    "type": "string",
                    "description": "可选:关键取舍/风险/需要用户先提供的信息,会显示在清单下方",
                },
            },
            "required": ["steps"],
        },
    },
    "ask_clarifying_question": {
        "risk_channel": "read",
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