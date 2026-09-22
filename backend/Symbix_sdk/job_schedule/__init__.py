"""定时任务 Job Schedule 包。

导出 JobScheduler / JobStorage / JobRunner 及 schema，并提供一个 JobManager 把三者串起来，
供 FastAPI 路由与 lifespan 使用。
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime
from typing import Optional

from .schema import (
    JobBase,
    JobCreate,
    JobUpdate,
    JobOut,
    JobHistoryItem,
    validate_trigger,
)
from .storage import JobStorage
from .scheduler import JobScheduler, _set_manager_ref
from .runner import JobRunner


class JobManager:
    """编排层：把 storage + scheduler + runner 绑定到 shared db，暴露业务 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.storage = JobStorage(db_path)
        self.scheduler = JobScheduler(db_path)
        self.runner: Optional[JobRunner] = None
        # 持有执行所需业务单例（在 build_runner 注入前为 None）
        self._deps: dict = {}

    # ------- 依赖注入（启动时 main.py 调用）-------
    def build(self, **deps) -> None:
        """注入 memory/tool_registry/... 等业务依赖，并构造 runner。deps 键见 runner.JobRunner。"""
        self._deps = deps
        if self.runner is None:
            self.runner = JobRunner(self.storage, self.scheduler, **deps)
            _set_manager_ref(self)

    def start(self) -> None:
        """恢复并启动:先把 apscheduler jobstore 与 job_meta 对齐,再装启用的 job。

        背景: job_meta 是业务真相源;apscheduler_jobs 是 APScheduler 的持久化副本。
        若两者不一致(前端已删但 jobstore 残留),旧 job 会在重启后幽灵复恢。
        这里以 job_meta 为准重建 jobstore,保证一致性。
        """
        if self.runner is None:
            raise RuntimeError("JobManager.build() 未调用(缺少业务依赖)")
        jobs = self.storage.list_meta()
        # 以 job_meta 为准:清掉 apscheduler 残留 job,再重新装载启用项
        self.scheduler.purge()
        for job in jobs:
            if job.get("enabled", True):
                try:
                    self.scheduler.add_job(job)
                except Exception as e:
                    print(f"[job] 恢复 job {job['id']} 失败: {e}")
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown()

    # ------- CRUD -------
    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex[:12]

    def create(self, data: JobCreate) -> dict:
        validate_trigger(data.trigger_type, data.trigger_config)
        job = data.model_dump()
        job["id"] = self._new_id()
        job["last_run_time"] = None
        job["last_status"] = None
        job["last_error"] = None
        self.storage.upsert_meta(job)
        if job.get("enabled", True) and self.scheduler.running:
            self.scheduler.add_job(job)
        return self._to_out(job)

    def update(self, job_id: str, data: JobUpdate) -> dict:
        existing = self.storage.get_meta(job_id)
        if not existing:
            raise KeyError(job_id)
        patch = data.model_dump(exclude_unset=True)
        existing.update(patch)
        if "trigger_type" in patch or "trigger_config" in patch:
            validate_trigger(existing["trigger_type"], existing["trigger_config"])
        self.storage.upsert_meta(existing)
        if self.scheduler.running:
            # 始终重建（覆盖 pause/resume/trigger/enabled 变化）
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass
            if existing.get("enabled", True):
                self.scheduler.add_job(existing)
        return self._to_out(existing)

    def delete(self, job_id: str) -> bool:
        # 1) APScheduler 内存 job + 它的持久化行(sqlite apscheduler_jobs 表)
        #    remove_job 会同步删掉 SQLAlchemyJobStore 里的持久化行
        self.scheduler.remove_job(job_id)
        # 2) 业务 meta 表
        deleted = self.storage.delete_meta(job_id)
        # 3) 历史记录一并清理,避免删了 job 还残留 history 行
        self.storage.delete_history(job_id)
        return deleted

    def delete_by_session(self, session_id: str) -> list[str]:
        """删除会话时级联:找到所有绑定该 session 的定时任务并彻底删除(含调度器与历史)。
        返回被删除的 job id 列表。区别于 release_session(仅解绑),这里任务本体也删。"""
        deleted = []
        for job in self.storage.list_meta():
            if job.get("session_id") == session_id:
                try:
                    self.delete(job["id"])
                    deleted.append(job["id"])
                except Exception as e:
                    print(f"[Jobs] delete_by_session failed for {job.get('id')}: {e}")
        return deleted

    def pause(self, job_id: str) -> dict:
        existing = self.storage.get_meta(job_id)
        if not existing:
            raise KeyError(job_id)
        existing["enabled"] = False
        self.storage.upsert_meta(existing)
        self.scheduler.pause_job(job_id)
        return self._to_out(existing)

    def resume(self, job_id: str) -> dict:
        existing = self.storage.get_meta(job_id)
        if not existing:
            raise KeyError(job_id)
        existing["enabled"] = True
        self.storage.upsert_meta(existing)
        if self.scheduler.running:
            try:
                self.scheduler.resume_job(job_id)
            except Exception:
                self.scheduler.add_job(existing)
        return self._to_out(existing)

    async def run_now(self, job_id: str) -> dict:
        """立即试跑一次（dev）。"""
        job = self.storage.get_meta(job_id)
        if not job:
            raise KeyError(job_id)
        if self.runner is None:
            raise RuntimeError("runner not built")
        await self.runner.execute(job)
        return self._to_out(job)

    def list(self) -> list[dict]:
        return [self._to_out(j) for j in self.storage.list_meta()]

    def get(self, job_id: str) -> dict:
        job = self.storage.get_meta(job_id)
        if not job:
            raise KeyError(job_id)
        return self._to_out(job)

    def history(self, job_id: str, limit: int = 20) -> list[dict]:
        return self.storage.list_history(job_id, limit)

    def release_session(self, session_id: str) -> list[str]:
        """会话被删除时解绑:找到所有关联该 session 的定时任务,解除其 session_id 引用。
        返回受影响 job id 列表(未删除任务本体,只断开引用)。"""
        released = []
        for job in self.storage.list_meta():
            if job.get("session_id") == session_id:
                job["session_id"] = None
                self.storage.upsert_meta(job)
                released.append(job["id"])
        return released

    def _to_out(self, job: dict) -> dict:
        out = dict(job)
        out["next_run_time"] = self.scheduler.get_next_run(job["id"])
        # datetime → iso(str) 便于 JSON 序列化
        for k in ("next_run_time", "last_run_time"):
            v = out.get(k)
            if isinstance(v, datetime):
                out[k] = v.isoformat()
            elif v is not None and not isinstance(v, str):
                out[k] = None
        return out


def _defaults():
    return {}


__all__ = [
    "JobManager",
    "JobStorage",
    "JobScheduler",
    "JobRunner",
    "JobBase",
    "JobCreate",
    "JobUpdate",
    "JobOut",
    "JobHistoryItem",
]