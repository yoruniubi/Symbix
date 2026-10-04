from __future__ import annotations
import json
import re
import uuid

# 选项点击行为:approve=直接确认 / reject=直接拒绝 / fill=填进输入框待用户改写
OPTION_ACTIONS = ("approve", "reject", "fill")
# 单张卡片最多展示的选项数(多了会挤,也超出用户一次能扫完的量)
MAX_OPTIONS = 6


def _normalize_options(raw, max_items: int = MAX_OPTIONS) -> list[dict]:
    """把模型给的选项归一化成 ``[{"label", "description", "action"}]``。

    兼容纯字符串、``{"label", "description"}`` 字典、以及带 ``action`` 的字典；
    action 不在白名单里一律留空(前端按默认行为处理)。选项去重并截断到 max_items。
    """
    if isinstance(raw, str):
        items = raw.splitlines()
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        items = []

    out: list[dict] = []
    seen: set[str] = set()
    for item in items:
        desc, action = "", ""
        if item is None:
            continue
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("text") or item.get("value") or "").strip()
            desc = str(item.get("description") or item.get("desc") or "").strip()
            action = str(item.get("action") or "").strip().lower()
        else:
            label = str(item).strip()
        # 去掉行首编号,避免出现「1. 1. xxx」
        label = re.sub(r"^\s*(?:\d+[.)、]|[-*•])\s*", "", label).strip()
        if not label or label in seen:
            continue
        seen.add(label)
        out.append(
            {
                "label": label,
                "description": desc,
                "action": action if action in OPTION_ACTIONS else "",
            }
        )
        if len(out) >= max_items:
            break
    return out


def ask_clarifying_question(
    question: str,
    suggestions: list | None = None,
    context: str = "",
) -> str:
    """向用户提出澄清问题，暂停当前任务等待用户回答。

    Args:
        question: 需要向用户确认的具体问题
        suggestions: 可选，2-4 个建议答案；可传字符串，
            也可传 ``{"label", "description"}`` 让卡片在选项下多显示一行说明
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

    options = _normalize_options(suggestions)
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
            # suggestions 保留纯文本(默认回答/旧前端兼容),options 带描述与点击行为
            "suggestions": [o["label"] for o in options],
            "options": options,
            "context": context.strip(),
            "message": "已向用户发起提问，等待回复后再继续",
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 计划确认(plan & solve 的「先提待办、等用户点头」)
# ---------------------------------------------------------------------------

# 计划确认卡的默认选项:label 是按钮文字,description 是选项下的一行说明,
# action 决定点击行为(approve=确认执行 / fill=填进输入框让用户补一句 / reject=先不动手)
PLAN_OPTIONS = [
    {"label": "按此执行", "description": "按清单从头执行,每完成一步汇报一次", "action": "approve"},
    {"label": "需要调整", "description": "在下方输入框写下要改的地方,我改完重新提交", "action": "fill"},
    {"label": "先不执行", "description": "这次先不动手,方案先留着", "action": "reject"},
]
# 纯文本形式的默认选项(默认回答等场景用)
PLAN_SUGGESTIONS = [o["label"] for o in PLAN_OPTIONS]


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
    options: list | None = None,
) -> str:
    """把待办清单提交给用户确认，暂停任务等待用户点头后再执行。

    Args:
        steps: 待办清单，数组或带编号的多行文本（2-8 条为宜）
        question: 可选，向用户提的问题，默认「我打算按下面这几步做，可以吗？」
        notes: 可选，补充说明（关键取舍、风险、需要用户先提供的东西）
        options: 可选，自己想给用户的选项卡（字符串或 ``{"label", "description"}``）；
            不传则用默认三选一(按此执行/需要调整/先不执行)。
            自定义选项点一下只是填进输入框,用户补一句再发,不会被当成「确认执行」。

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

    # 模型自己给的选项卡一律不带 action(前端只填进输入框),
    # 避免「先只做第 1 步」这类话被当成「按原计划执行」直接确认。
    plan_options = _normalize_options(options) or [dict(o) for o in PLAN_OPTIONS]
    plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(plan, 1))
    return json.dumps(
        {
            "status": "pending_user_input",
            "id": request_id,
            # kind=plan 让前端渲染成「执行计划确认」卡,而不是普通提问
            "kind": "plan",
            "question": question,
            "plan": plan,
            "suggestions": [o["label"] for o in plan_options],
            "options": plan_options,
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
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "description": "选项文字(短,一行内)"},
                            "description": {"type": "string", "description": "可选:选项下的一行说明"},
                        },
                        "required": ["label"],
                    },
                    "description": (
                        "可选:你想给用户的选项卡(最多 6 个),不传则用默认三选一。"
                        "想让用户挑不同做法时才传,例如「先只做第 1 步」「换个方案不依赖外部 API」;"
                        "用户点自定义选项只是把它填进输入框,不会被当成确认执行"
                    ),
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
            "前端会渲染成可点选的选项列表(想更清楚可在选项下附一句 description)；"
            "开放式问题可不传 suggestions。"
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
                    "items": {
                        "anyOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string", "description": "选项文字"},
                                    "description": {"type": "string", "description": "可选:选项下的一行说明"},
                                },
                                "required": ["label"],
                            },
                        ]
                    },
                    "description": (
                        "可选：2-4 个建议答案/选项，供用户快速点选；"
                        "想要更清楚可在选项下附一句 description"
                    ),
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