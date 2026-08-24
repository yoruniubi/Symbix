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
    """返回合并后的生效规则(默认 + override)。

    为避免把“防御性默认规则”当成已安装工具展示(例如 run_command /
    execute_command / exec_command 等通用命令名在本项目并未实现),
    这里只保留两类:真实已在当前运行时注册的工具,以及用户手动添加的
    override(即使该工具名当前未安装,也应继续展示与编辑)。
    """
    overrides = get_overrides()
    installed = _installed_tool_names()
    rules = get_effective_rules()
    # 只展示“当前真实已注册工具”的规则(含其对应用户 override)。
    # 其余默认规则(run_command/execute_command/exec_command/write_to_file 等)
    # 是分类器为未知/通用名准备的防御性兜底,并非本项目已实现工具,
    # 展示出来会让列表充斥着用不到的条目并误导使用者。
    filtered = {
        name: rule
        for name, rule in rules.items()
        if name in installed
    }
    return {"rules": filtered, "overrides": overrides}


def _installed_tool_names() -> set:
    """收集当前运行时真实可调用的工具名(native + skill + mcp)。"""
    from application.state import tool_registry

    names: set = set()
    try:
        for t in tool_registry.get_openai_tools():
            fn = t.get("function", {}).get("name")
            if fn:
                names.add(fn)
    except Exception:
        pass
    return names


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
