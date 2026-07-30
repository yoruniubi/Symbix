# tools/pet_tools.py
"""桌宠控制工具：emit_pet_action"""
from __future__ import annotations
import json


# 与 spritesheet / 前端 Home.vue 对齐；语义别名会在总线侧归一化
PET_ACTION_ENUM = [
    "idle",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "review",
    "running",
    "runningRight",
    "runningLeft",
    "happy",      # → jumping
    "thinking",   # → review
    "sad",        # → failed
    "celebrate",  # → jumping
    "wave",       # → waving
    "jump",       # → jumping
    "error",      # → failed
]


def emit_pet_action(action: str, bubble: str = "") -> str:
    """触发桌宠动画/表情，经事件总线推送到 Home 窗口 SSE。

    Args:
        action: 动作名（见 PET_ACTION_ENUM；别名会映射到真实 spritesheet 行）
        bubble: 可选气泡文案（前端显示约 3 秒）
    """
    action = (action or "").strip()
    if not action:
        return json.dumps(
            {"status": "error", "message": "action 不能为空"},
            ensure_ascii=False,
        )

    try:
        # application 层事件总线（backend 进程内可用）
        from application.pet_action import pet_action, normalize_pet_action

        event = pet_action.emit(
            action,
            bubble=bubble or "",
            source="emit_pet_action",
        )
        normalized = event.get("action") or normalize_pet_action(action)
        return json.dumps(
            {
                "status": "ok",
                "action": normalized,
                "raw_action": action,
                "bubble": event.get("bubble") or "",
                "id": event.get("id"),
                "subscribers": "sse:/pet/events",
                "message": f"已触发桌宠动作: {normalized}"
                + (f"（气泡: {event['bubble']}）" if event.get("bubble") else ""),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        # 无 application 上下文时仍返回可解析结果，便于单测
        return json.dumps(
            {
                "status": "queued_local",
                "action": action,
                "bubble": (bubble or "").strip(),
                "message": f"已记录桌宠动作: {action}（事件总线不可用: {e}）",
            },
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

PET_TOOLS_SCHEMAS = {
    "emit_pet_action": {
        "func": emit_pet_action,
        "description": (
            "触发桌宠动画/表情并推送到主窗口。"
            "在对话中表达情绪、完成任务庆祝、失败遗憾、思考中、打招呼时调用。"
            "可用动作: idle/waving/jumping/failed/waiting/review/running，"
            "以及别名 happy→jumping、thinking→review、sad/error→failed、celebrate→jumping。"
            "可选 bubble 显示短气泡文案。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": PET_ACTION_ENUM,
                    "description": (
                        "动作类型。优先用真实动作名；"
                        "happy/thinking/sad/celebrate 等别名会自动映射。"
                    ),
                },
                "bubble": {
                    "type": "string",
                    "description": "可选：桌宠头顶短气泡（中文，≤40字）",
                },
            },
            "required": ["action"],
        },
    },
}