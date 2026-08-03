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

def check_agent_status(status: str) -> dict:
    """检查 Agent 当前的状态。

    Args:
        status: 状态描述，如 "thinking"、"idle"、"celebrate"、"error"

    Returns:
        包含状态信息和推荐动作的字典
    """
    status = (status or "").strip().lower()
    if not status:
        return {"status": "unknown", "message": "未提供状态", "action": "idle"}

    # 状态 → 动画映射
    status_map = {
        "thinking": {"status": "thinking", "message": "Agent 正在思考中…", "action": "review"},
        "review": {"status": "thinking", "message": "Agent 正在思考中…", "action": "review"},
        "idle": {"status": "idle", "message": "Agent 空闲中", "action": "idle"},
        "celebrate": {"status": "celebrate", "message": "Agent 完成任务！", "action": "jumping"},
        "done": {"status": "celebrate", "message": "Agent 完成任务！", "action": "jumping"},
        "complete": {"status": "celebrate", "message": "Agent 完成任务！", "action": "jumping"},
        "success": {"status": "celebrate", "message": "Agent 完成任务！", "action": "jumping"},
        "error": {"status": "error", "message": "Agent 遇到错误", "action": "failed"},
        "failed": {"status": "error", "message": "Agent 遇到错误", "action": "failed"},
        "working": {"status": "working", "message": "Agent 正在工作中…", "action": "idle"},
        "busy": {"status": "working", "message": "Agent 正在工作中…", "action": "idle"},
    }

    result = status_map.get(status, {"status": "unknown", "message": f"未知状态: {status}", "action": "idle"})
    # 确保 action 是有效值
    if result["action"] not in ["idle", "waving", "jumping", "failed", "waiting", "review", "running", "runningRight", "runningLeft"]:
        result["action"] = "idle"
    return result


def play_status_animation(status: str, bubble_override: str = "") -> str:
    """根据 Agent 状态触发对应的桌宠动画。

    这是 check_agent_status + emit_pet_action 的组合工具，
    用于在 Agent 状态变化时自动驱动桌宠表情。

    Args:
        status: 状态值，如 "thinking"、"idle"、"celebrate"、"error"
        bubble_override: 可选，覆盖默认气泡文案

    Returns:
        emit_pet_action 的 JSON 结果
    """
    status = (status or "").strip().lower()
    if not status:
        return emit_pet_action("idle", bubble="状态未知，保持空闲")

    # 用 check_agent_status 获取映射
    info = check_agent_status(status)
    action = info.get("action", "idle")
    bubble = bubble_override or info.get("message", "")

    return emit_pet_action(action, bubble=bubble)

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
    "check_agent_status": {
        "func": check_agent_status,
        "description": (
            "检查 Agent 当前状态，返回状态信息和推荐桌宠动作。"
            "适用于在工作流中需要判断 Agent 行为状态时调用。"
            "支持状态: thinking/review → 思考中, idle → 空闲, "
            "celebrate/done/complete/success → 完成任务, error/failed → 错误, "
            "working/busy → 工作中。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Agent 状态描述，如 thinking、idle、celebrate、error、done、complete、success、failed、working、busy",
                },
            },
            "required": ["status"],
        },
    },
    "play_status_animation": {
        "func": play_status_animation,
        "description": (
            "根据 Agent 状态触发对应的桌宠动画。"
            "是 check_agent_status + emit_pet_action 的组合工具，"
            "自动将状态映射到合适的动画和气泡文案。"
            "例如: thinking → review 思考动画, celebrate → jumping 跳跃庆祝, "
            "error → failed 失败动画。"
            "推荐在 Agent 状态切换时自动调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Agent 状态值，如 thinking、idle、celebrate、error、done、complete、success、failed、working、busy",
                },
                "bubble_override": {
                    "type": "string",
                    "description": "可选，覆盖默认气泡文案。留空则使用默认文案",
                },
            },
            "required": ["status"],
        },
    },
}
