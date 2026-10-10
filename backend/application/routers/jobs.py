from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from Symbix_sdk.job_schedule.schema import JobCreate, JobUpdate, validate_trigger
from Symbix_sdk.job_schedule.humanize import describe_trigger, next_run_times, parse_schedule
router = APIRouter(prefix="/jobs", tags=["jobs"])

class SchedulePreviewRequest(BaseModel):
    """预览请求:二选一——自然语言 schedule,或已规范化的 trigger_type + trigger_config。"""
    schedule: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_config: Optional[dict] = None
    count: int = 3

# 由 main.py 在 startup 时注入
job_manager = None


def _set_manager(mgr) -> None:
    global job_manager
    job_manager = mgr


def _get_manager():
    if job_manager is None:
        raise HTTPException(status_code=503, detail="job manager not initialized")
    return job_manager


@router.post("/preview")
async def preview_schedule(body: SchedulePreviewRequest):
    """把「人话时间」或 trigger 翻译成规范 config,并给出接下来几次运行时间(面板实时预览用)。"""
    try:
        if (body.schedule or "").strip():
            parsed = parse_schedule(body.schedule or "")
            trigger_type, trigger_config = parsed["trigger_type"], parsed["trigger_config"]
        else:
            if not body.trigger_type:
                raise ValueError("需要 schedule(人话时间) 或 trigger_type + trigger_config")
            trigger_type = body.trigger_type
            trigger_config = body.trigger_config or {}
            validate_trigger(trigger_type, trigger_config)
        return {
            "status": "ok",
            "trigger_type": trigger_type,
            "trigger_config": trigger_config,
            "label": describe_trigger(trigger_type, trigger_config),
            "next_runs": next_run_times(trigger_type, trigger_config, body.count),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_job(body: JobCreate):
    mgr = _get_manager()
    try:
        job = mgr.create(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return job


@router.get("")
async def list_jobs():
    return _get_manager().list()


@router.get("/{job_id}")
async def get_job(job_id: str):
    try:
        return _get_manager().get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@router.patch("/{job_id}")
async def update_job(job_id: str, body: JobUpdate):
    try:
        return _get_manager().update(job_id, body)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{job_id}")
async def delete_job(job_id: str):
    if not _get_manager().delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return {"status": "ok"}


@router.post("/{job_id}/pause")
async def pause_job(job_id: str):
    try:
        return _get_manager().pause(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@router.post("/{job_id}/resume")
async def resume_job(job_id: str):
    try:
        return _get_manager().resume(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")


@router.post("/{job_id}/run")
async def run_job(job_id: str):
    """立即执行:后台跑并立刻返回,前端轮询 /jobs 的 running 字段直到跑完。"""
    try:
        return _get_manager().start_run(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/{job_id}/history")
async def job_history(job_id: str, limit: int = 20):
    return _get_manager().history(job_id, limit)