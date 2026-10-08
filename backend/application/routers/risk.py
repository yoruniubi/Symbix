from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from Symbix_sdk.tools.risk_classifier import (
    classify_tool_risk,
    get_effective_rules,
    get_overrides,
    set_override,
    remove_override,
)
from application.services.risk_context import (
    get_session_trust,
    clear_session,
    set_server_trusted,
    is_server_trusted,
    list_sessions_trust,
)

router = APIRouter(prefix="/risk", tags=["risk"])


class OverrideRequest(BaseModel):
    tool_name: str
    level: Literal["safe", "medium", "high"]
    reason: str = ""


class ClassifyRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


class FullRulesRequest(BaseModel):
    tool_names: list[str]


class TrustModeRequest(BaseModel):
    session_id: str
    mode: Literal["normal", "auto"]


class ServerTrustRequest(BaseModel):
    server_id: str
    trusted: bool


@router.get("/session-trust")
async def get_all_session_trust() -> dict:
    """返回所有会话的信任状态(面板展示用)。"""
    return {"sessions": list_sessions_trust()}


@router.get("/session-trust/{session_id}")
async def get_session_trust_api(session_id: str) -> dict:
    """返回单会话信任状态。"""
    return get_session_trust(session_id).to_dict()


@router.post("/session-trust/mode")
async def set_trust_mode(req: TrustModeRequest) -> dict:
    """切换会话信任模式: normal(默认逐个问) / auto(auto-pilot 会话级开关)。"""
    st = get_session_trust(req.session_id)
    st.set_mode(req.mode)
    return {"status": "ok", "session_id": req.session_id, "trust": st.to_dict()}


@router.delete("/session-trust/{session_id}")
async def reset_session_trust(session_id: str) -> dict:
    """清除某会话的信任状态(回 normal + 清 grants)。"""
    clear_session(session_id)
    return {"status": "ok"}


@router.get("/server-trust/{server_id}")
async def get_server_trust(server_id: str) -> dict:
    """查询某 MCP server 是否被用户信任。"""
    return {"server_id": server_id, "trusted": is_server_trusted(server_id)}


@router.put("/server-trust/{server_id}")
async def put_server_trust(server_id: str, req: ServerTrustRequest) -> dict:
    """标记/取消标记某 MCP server 为 trusted(trust 降级时自动清其 grants)。"""
    ok = set_server_trusted(server_id, req.trusted)
    if not ok:
        raise HTTPException(status_code=404, detail=f"server '{server_id}' not found")
    return {"status": "ok", "server_id": server_id, "trusted": req.trusted}


@router.get("/rules")
async def list_rules() -> dict:
    """返回合并后的生效规则(默认 + override)。"""
    return {"rules": get_effective_rules(), "overrides": get_overrides()}


@router.post("/rules/full")
async def list_full_rules(req: FullRulesRequest) -> dict:
    """
    返回给定工具全集(含未配置的陌生工具)的生效规则。

    每个工具都会跑 classify_tool_risk 得到 level/reason(含 unknown 的 MIDIUM fallback);
    若该工具存在 override,再补 source="override" 与 override 的 reason。
    """
    overrides = get_overrides()
    rules: dict = {}
    for name in req.tool_names:
        name = name.strip()
        if not name:
            continue
        _r = classify_tool_risk(name, {})
        level, reason, channel = _r.level, _r.reason, _r.channel
        ov = overrides.get(f"builtin:{name}") or overrides.get(name)
        if ov:
            rules[name] = {
                "level": ov.get("level", level),
                "reason": ov.get("reason", "") or reason,
                "source": "override",
                "channel": channel,
            }
        else:
            rules[name] = {
                "level": level,
                "reason": reason,
                "source": "default",
                "channel": channel,
            }
    return {"rules": rules, "overrides": overrides}



@router.post("/override")
async def add_override(req: OverrideRequest) -> dict:
    """新增/更新一条 override 规则。"""
    try:
        set_override(req.tool_name, req.level, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok", "rules": get_effective_rules()}


@router.delete("/override/{tool_name}")
async def delete_override(tool_name: str) -> dict:
    """删除一条 override，恢复默认。"""
    removed = remove_override(tool_name)
    if not removed:
        raise HTTPException(status_code=404, detail="override not found")
    return {"status": "ok", "rules": get_effective_rules()}


@router.post("/classify")
async def classify(req: ClassifyRequest) -> dict:
    """试测：给定工具名 + 参数，返回分级结果。"""
    _r = classify_tool_risk(req.tool_name, req.arguments)
    return {"tool_name": req.tool_name, "level": _r.level, "reason": _r.reason, "channel": _r.channel, "confidence": _r.confidence}
