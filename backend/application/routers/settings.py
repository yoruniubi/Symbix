"""设置页里需要落到后端的运行时配置。

目前只有「长任务」档位:轮次上限与累积工具结果 token 预算。
存在 config/runtime_config.json,改完下一个请求就生效(不用重启)。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from Symbix_sdk.config.runtime_config import MODES, PRESETS, runtime_config

router = APIRouter(tags=["settings"])


@router.get("/settings/long-task")
async def get_long_task():
    """当前档位 + 可选项(带各自的数值,前端直接展示)。"""
    return {
        "config": runtime_config.cfg.to_dict(),
        "modes": [{"mode": mode, **PRESETS[mode]} for mode in MODES],
    }


class LongTaskPatch(BaseModel):
    mode: str


@router.put("/settings/long-task")
async def update_long_task(patch: LongTaskPatch):
    if patch.mode not in PRESETS:
        raise HTTPException(status_code=400, detail=f"未知档位: {patch.mode}")
    runtime_config.apply_patch({"mode": patch.mode})
    return {"status": "ok", "config": runtime_config.cfg.to_dict()}
