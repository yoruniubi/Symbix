from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from .schema import validate_trigger

log = logging.getLogger("job_schedule")

# 由 JobManager 在 start() 时注入，供模块级调度函数回调。
_manager_ref: Optional["object"] = None


def _set_manager_ref(mgr) -> None:
    global _manager_ref
    _manager_ref = mgr


def build_trigger(trigger_type: str, cfg: dict):
    """根据 trigger_type + config 构造 APScheduler trigger。"""
    validate_trigger(trigger_type, cfg)
    if trigger_type == "cron":
        return CronTrigger(**cfg)
    if trigger_type == "interval":
        return IntervalTrigger(**cfg)
    if trigger_type == "date":
        run_date = cfg["run_date"]
        if isinstance(run_date, str):
            run_date = datetime.fromisoformat(run_date)
        return DateTrigger(run_date)
    raise ValueError(f"未知 trigger_type: {trigger_type}")


async def _dispatch_job(job_id: str) -> None:
    """到点回调（模块级，可 pickle）。从 manager 取 meta 交给 runner。"""
    mgr = _manager_ref
    if mgr is None or mgr.runner is None:
        log.error("job runner not set, job %s skipped", job_id)
        return
    job = mgr.storage.get_meta(job_id)
    if not job:
        log.warning("job %s not found in meta, skipped", job_id)
        return
    if not job.get("enabled", True):
        return
    try:
        await mgr.runner.execute(job)
    except Exception:
        import traceback
        traceback.print_exc()


class JobScheduler:
    def __init__(self, jobs_db_path: str) -> None:
        self.jobs_db_path = jobs_db_path
        jobstore = SQLAlchemyJobStore(url=f"sqlite:///{jobs_db_path}")
        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 60,
            },
        )
        self._scheduler.add_jobstore(jobstore, "default")

    @property
    def running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            log.info("JobScheduler started")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("JobScheduler stopped")

    def purge(self) -> None:
        """清空 jobstore 里所有 job(启动对齐用)。

        注意: APScheduler 的 scheduler.remove_all_jobs() 在未启动(STATE_STOPPED)
        时只清内存 pending 列表、不删持久化行。这里必须直接调用 jobstore 的
        remove_all_jobs(),才能真正清掉 sqlite apscheduler_jobs 残留。
        """
        try:
            store = self._scheduler._jobstores.get("default")
            if store is not None:
                store.remove_all_jobs()
            self._scheduler.remove_all_jobs()
            log.info("JobScheduler jobstore purged")
        except Exception as e:
            # 全新安装: apscheduler_jobs 表由 SQLAlchemyJobStore 在 start() 时才创建,
            # 首启动时本来就没有残留可清,降为 debug 避免吓人的 warning
            if "no such table" in str(e):
                log.debug("JobScheduler jobstore 尚未创建(全新安装),跳过 purge")
            else:
                log.warning("JobScheduler purge failed: %s", e)

    def add_job(self, job: dict) -> None:
        trigger = build_trigger(job["trigger_type"], job["trigger_config"])
        self._scheduler.add_job(
            _dispatch_job,
            trigger=trigger,
            id=job["id"],
            kwargs={"job_id": job["id"]},
            replace_existing=True,
        )

    def update_job(self, job: dict) -> None:
        trigger = build_trigger(job["trigger_type"], job["trigger_config"])
        self._scheduler.reschedule_job(job["id"], trigger=trigger)

    def remove_job(self, job_id: str) -> None:
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass

    def pause_job(self, job_id: str) -> None:
        try:
            self._scheduler.pause_job(job_id)
        except Exception:
            pass

    def resume_job(self, job_id: str) -> None:
        try:
            self._scheduler.resume_job(job_id)
        except Exception:
            pass

    def get_next_run(self, job_id: str) -> Optional[datetime]:
        try:
            job = self._scheduler.get_job(job_id)
            return job.next_run_time if job else None
        except Exception:
            return None