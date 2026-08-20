"""风险分级管理路由：查看生效规则 / 增删 override / 试测分级。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal

from Symbix_sdk.tools.risk_classifier import (
    classify_tool_risk,
    get_effective_rules,
    get_overrides,
    set_override,
    remove_override,
    ToolRiskLevel,
)

router = APIRouter(prefix="/risk", tags=["risk"])


class OverrideRequest(BaseModel):
    tool_name: str
    level: Literal["safe", "medium", "high"]
    reason: str = ""


class ClassifyRequest(BaseModel):
    tool_name: str
    arguments: dict = {}


@router.get("/rules")
async def list_rules() -> dict:
    """返回合并后的生效规则（默认 + override）。"""
    return {"rules": get_effective_rules(), "overrides": get_overrides()}


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
    level, reason = classify_tool_risk(req.tool_name, req.arguments)
    return {"tool_name": req.tool_name, "level": level, "reason": reason}
