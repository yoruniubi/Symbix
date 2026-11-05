from __future__ import annotations
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field


TriggerType = Literal["cron", "interval", "date"]


class JobBase(BaseModel):
    """Job 基本字段（创建/更新通用）。"""
    name: str = Field(..., min_length=1, max_length=120)
    trigger_type: TriggerType
    trigger_config: dict = Field(default_factory=dict)
    prompt: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    enabled: bool = True
    auto_safe: bool = True


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    """部分更新；None 字段表示不改动。"""
    name: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    prompt: Optional[str] = None
    session_id: Optional[str] = None
    enabled: Optional[bool] = None
    auto_safe: Optional[bool] = None


class JobOut(JobBase):
    """对外返回的 Job 视图（含运行时状态）。"""
    id: str
    next_run_time: Optional[datetime] = None
    last_run_time: Optional[datetime] = None
    last_status: Optional[Literal["ok", "error", "skipped"]] = None
    last_error: Optional[str] = None
    # 一次性任务「已跑过」:不再重排
    completed: bool = False
    # 当前是否有一次执行正在进行(定时到点或「立即执行」)
    running: bool = False
    # 人话频率回显（「每天 09:00」），由 humanize.describe_trigger 生成
    trigger_label: Optional[str] = None


class JobHistoryItem(BaseModel):
    job_id: str
    run_time: datetime
    status: Literal["ok", "error", "skipped"]
    output_snippet: str = ""
    error: str = ""


def validate_trigger(trigger_type: TriggerType, cfg: dict) -> None:
    """校验 trigger_config 字段合法性。"""
    if trigger_type == "cron":
        # 支持 cron 字段子集
        allowed = {"year", "month", "day", "week", "day_of_week", "hour", "minute", "second"}
        bad = set(cfg.keys()) - allowed
        if bad:
            raise ValueError(f"cron trigger 不支持字段: {bad}")
        if not cfg:
            raise ValueError("cron trigger 需要至少一个时间字段")
    elif trigger_type == "interval":
        allowed = {"weeks", "days", "hours", "minutes", "seconds"}
        bad = set(cfg.keys()) - allowed
        if bad:
            raise ValueError(f"interval trigger 不支持字段: {bad}")
        if not cfg:
            raise ValueError("interval trigger 需要至少一个时间字段")
    elif trigger_type == "date":
        if "run_date" not in cfg:
            raise ValueError("date trigger 需要 run_date 字段")
    else:
        raise ValueError(f"未知 trigger_type: {trigger_type}")
