from __future__ import annotations
import json
from Symbix_sdk.checkpoint import get_current
from Symbix_sdk.job_schedule.humanize import describe_trigger, next_run_times, parse_schedule

# main.py lifespan 里注入(application.state.job_manager)
_manager = None


def set_job_manager(mgr) -> None:
    """注入 JobManager;重复注入时覆盖(热重载友好)。"""
    global _manager
    _manager = mgr


def _get_manager():
    if _manager is None:
        raise RuntimeError(
            "定时任务调度器尚未就绪(后端刚启动或启动失败)。"
            "可以告诉用户稍后再试,或让用户在前端「定时任务」面板手动创建。"
        )
    return _manager


def _json(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _resolve_job(mgr, ref: str) -> dict:
    """按 id / id 前缀 / 名称 找任务;找不到或名字不唯一时抛 ValueError(带候选)。"""
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("请给出任务 id 或名称")
    jobs = mgr.storage.list_meta()

    for job in jobs:  # 完整 id
        if job["id"] == ref:
            return job
    prefix = [j for j in jobs if j["id"].startswith(ref)]
    if len(prefix) == 1:
        return prefix[0]
    exact = [j for j in jobs if (j.get("name") or "").strip() == ref]
    if len(exact) == 1:
        return exact[0]
    partial = [j for j in jobs if ref in (j.get("name") or "")]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1 or len(prefix) > 1:
        cands = partial or prefix
        names = "、".join(f"{j.get('name')}({j['id']})" for j in cands[:6])
        raise ValueError(f"「{ref}」匹配到多个任务:{names}。请用完整 id 指定")
    if not jobs:
        raise ValueError("当前没有任何定时任务")
    names = "、".join(f"{j.get('name')}({j['id']})" for j in jobs[:6])
    raise ValueError(f"没找到「{ref}」这个任务。现有任务:{names}")


def create_schedule_job(name: str, schedule: str, prompt: str) -> str:
    """创建一个定时任务。schedule 用自然语言时间(每天 9:00 / 每 2 小时 / 每周一 8:30 …)。"""
    try:
        mgr = _get_manager()
    except RuntimeError as e:
        return _json({"status": "error", "message": str(e)})

    name = (name or "").strip()
    prompt = (prompt or "").strip()
    if not name:
        return _json({"status": "error", "message": "任务名称不能为空"})
    if not prompt:
        return _json({"status": "error", "message": "任务内容(prompt)不能为空,否则到点没东西可执行"})

    try:
        parsed = parse_schedule(schedule)
    except ValueError as e:
        return _json({"status": "error", "message": f"时间没解析成功:{e}"})

    trigger_type = parsed["trigger_type"]
    trigger_config = parsed["trigger_config"]

    # 绑定发起对话的会话(读不到上下文时留空,runner 会自动建一个 schedule__<id> 会话)
    session_id = ""
    try:
        session_id, _round_id = get_current()
    except Exception:
        session_id = ""

    from Symbix_sdk.job_schedule.schema import JobCreate

    dup = [j["id"] for j in mgr.storage.list_meta() if (j.get("name") or "") == name]
    try:
        body = JobCreate(
            name=name,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            prompt=prompt,
            session_id=session_id or None,
            enabled=True,
            auto_safe=True,
        )
        job = mgr.create(body)
    except ValueError as e:
        return _json({"status": "error", "message": f"创建失败:{e}"})
    except Exception as e:
        return _json({"status": "error", "message": f"创建失败:{type(e).__name__}: {e}"})

    try:
        upcoming = next_run_times(trigger_type, trigger_config, 3)
    except Exception:
        upcoming = []

    return _json({
        "status": "ok",
        "id": job["id"],
        "name": job["name"],
        "schedule": describe_trigger(trigger_type, trigger_config),
        "trigger_type": trigger_type,
        "trigger_config": trigger_config,
        "next_runs": upcoming,
        "session_id": job.get("session_id"),
        "auto_safe": True,
        "note": (
            "已加入定时任务(前端「定时任务」面板可见)。无人值守执行时只允许只读/无副作用操作,"
            "写入或执行命令会跳过并提示人工处理。"
            + (f" 注意:已存在同名任务 {dup},如需替换请先取消旧的。" if dup else "")
        ),
    })


def list_schedule_jobs() -> str:
    """列出当前所有定时任务(id / 名称 / 频率 / 下次运行 / 是否启用 / 上次结果)。"""
    try:
        mgr = _get_manager()
    except RuntimeError as e:
        return _json({"status": "error", "message": str(e)})

    items = []
    for job in mgr.storage.list_meta():
        out = mgr._to_out(job)
        items.append({
            "id": job["id"],
            "name": job.get("name"),
            "schedule": describe_trigger(job.get("trigger_type"), job.get("trigger_config") or {}),
            "prompt": job.get("prompt"),
            "enabled": bool(job.get("enabled", True)),
            "next_run_time": out.get("next_run_time"),
            "last_run_time": out.get("last_run_time"),
            "last_status": job.get("last_status"),
            "last_error": job.get("last_error"),
        })
    return _json({"status": "ok", "count": len(items), "jobs": items})


def cancel_schedule_job(job: str) -> str:
    """按 id 或名称取消(彻底删除)一个定时任务。"""
    try:
        mgr = _get_manager()
    except RuntimeError as e:
        return _json({"status": "error", "message": str(e)})
    try:
        target = _resolve_job(mgr, job)
    except ValueError as e:
        return _json({"status": "error", "message": str(e)})
    try:
        mgr.delete(target["id"])
    except Exception as e:
        return _json({"status": "error", "message": f"删除失败:{type(e).__name__}: {e}"})
    return _json({
        "status": "ok",
        "deleted": {"id": target["id"], "name": target.get("name"),
                    "schedule": describe_trigger(target.get("trigger_type"), target.get("trigger_config") or {})},
        "note": "任务与其执行历史已一并删除。若只想临时停用,可在前端面板用暂停。",
    })


# ---------------------------------------------------------------------------
# 工具 schema 注册表
# ---------------------------------------------------------------------------

JOB_TOOLS_SCHEMAS = {
    "create_schedule_job": {
        "risk_channel": "write",
        "func": create_schedule_job,
        "description": (
            "为用户创建一个定时任务(到点自动执行 prompt 内容)。"
            "当用户说「每天 9 点提醒我…」「每 2 小时检查一次…」「每周一上午给我…」「30 分钟后提醒我…」时调用。"
            "schedule 直接写自然语言时间,支持:每天 9:00 / 每天早上8点30 / 每周一三五 8:30 / 工作日 9:00 / "
            "周末 10点 / 每月1号 9:00 / 每月最后一天 / 每 30 分钟 / 每 2 小时 / 30分钟后 / 明天 9:00 / "
            "2026-10-05 09:00 / cron: 0 9 * * 1-5。"
            "prompt 要写成一句可独立执行的指令(无人值守执行,不能依赖后续对话);"
            "任务只允许只读/无副作用操作。创建前请把「频率 + 内容」跟用户确认一次。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "任务名称,如「喝水提醒」"},
                "schedule": {"type": "string", "description": "自然语言时间,如「每天 9:00」「每 2 小时」「每周一 8:30」"},
                "prompt": {"type": "string", "description": "到点要执行的指令,如「提醒我喝水并说一句关心的话」"},
            },
            "required": ["name", "schedule", "prompt"],
        },
    },
    "list_schedule_jobs": {
        "risk_channel": "read",
        "func": list_schedule_jobs,
        "description": "列出当前所有定时任务(名称/频率/下次运行时间/启用状态/上次执行结果)。用户问「我有哪些定时任务」时使用。",
        "parameters": {"type": "object", "properties": {}},
    },
    "cancel_schedule_job": {
        "risk_channel": "write",
        "func": cancel_schedule_job,
        "description": "取消(删除)一个定时任务。参数可给任务 id 或名称;名称有歧义时返回候选列表让用户确认。",
        "parameters": {
            "type": "object",
            "properties": {
                "job": {"type": "string", "description": "任务 id 或名称"},
            },
            "required": ["job"],
        },
    },
}
