"""定时任务 Job Schedule 路由：CRUD / pause / resume / run / history。"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from Symbix_sdk.job_schedule.schema import JobCreate, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])

# 由 main.py 在 startup 时注入
job_manager = None


def _set_manager(mgr) -> None:
    global job_manager
    job_manager = mgr


def _get_manager():
    if job_manager is None:
        raise HTTPException(status_code=503, detail="job manager not initialized")
    return job_manager


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
    try:
        return await _get_manager().run_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="job not found")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/{job_id}/history")
async def job_history(job_id: str, limit: int = 20):
    return _get_manager().history(job_id, limit)