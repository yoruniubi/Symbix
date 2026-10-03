from contextlib import asynccontextmanager
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.server import Server as UvicornServer
from application.services.pet_action import pet_action
from application.state import (
    mcp_manager,
    job_manager,
    memory,
    tool_registry,
    skill_registry,
    symbix_client,
    provider_registry,
    checkpoint_recorder,
)
import sys
import os
from application.routers import chat, providers, mcp, skills, sessions, pet, files, checkpoint, risk, jobs, voice, journal, danmaku


def _ensure_bundled_runtime_on_path() -> None:
    """将 SDK 捆绑运行时目录(bun.exe / uv.exe)注入 PATH。

    skill 脚本(open_terminal 里的 `uv run ...` / `bun x ...`)与
    stdio MCP 子进程都继承本后端进程的环境;注入后即使系统未装
    node / pip,也能靠 SDK 内置的 bun.exe / uv.exe 拉起 uv / uvx /
    bunx 语义的命令,不再依赖用户机器预装运行时。
    """
    try:
        from Symbix_sdk.resource_path import resource
        sdk_dir = str(resource("Symbix_sdk"))
    except Exception as e:
        print(f"[runtime] SDK 路径解析失败,跳过 PATH 注入: {e}")
        return
    if not os.path.isdir(sdk_dir):
        return
    path = os.environ.get("PATH", "")
    if sdk_dir in path:
        return
    os.environ["PATH"] = sdk_dir + os.pathsep + path
    print(f"[runtime] SDK 运行时目录已加入 PATH: {sdk_dir}")


_ensure_bundled_runtime_on_path()


def _force_close_sse(reason: str = "") -> None:
    """立刻掐断全部 /pet/events SSE，避免 reload 卡在 Waiting for connections。"""
    try:
        pet_action.close_all()
        suffix = f" ({reason})" if reason else ""
        print(f"[pet] SSE subscribers closed{suffix}")
    except Exception as e:
        print(f"[pet] close_all failed: {e}")

_orig_server_shutdown = UvicornServer.shutdown


async def _shutdown_close_sse_first(self, sockets=None):  # type: ignore[no-untyped-def]
    _force_close_sse("Server.shutdown")
    # 强制缩短优雅关闭等待，防止仍有连接拖死 reload（Windows 上尤其明显）
    try:
        if getattr(self.config, "timeout_graceful_shutdown", None) in (None, 0):
            self.config.timeout_graceful_shutdown = 1
    except Exception:
        pass
    return await _orig_server_shutdown(self, sockets=sockets)


UvicornServer.shutdown = _shutdown_close_sse_first  # type: ignore[method-assign]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期:退出时再兜底关一次 SSE + MCP。"""
    # 陪伴:空闲弹幕 + 时段问候定时器(每 60s 检查一次)
    _danmaku_task: asyncio.Task | None = None

    async def _companion_loop():
        import datetime as _dt
        from application.services.danmaku_service import emit_idle_danmaku_if_quiet, emit_danmaku, greeting_kind
        greeted_hour = -1  # 每个小时档只问候一次
        while True:
            try:
                now = _dt.datetime.now()
                hour = now.hour
                # 时段问候:整点进入新档时提示一次(greeting_kind 是纯判断,不消耗文案池)
                kind = greeting_kind(hour)
                if hour != greeted_hour and kind:
                    emit_danmaku(kind)
                    greeted_hour = hour
                # 空闲提醒:间隔取配置(danmaku_config.json idle_interval_s)
                from application.services.danmaku_service import danmaku_cfg as _dm_cfg
                emit_idle_danmaku_if_quiet(min_interval_s=float(_dm_cfg.cfg.idle_interval_s or 600))
            except Exception:
                pass
            await asyncio.sleep(60)

    try:
        _danmaku_task = asyncio.create_task(_companion_loop())
    except Exception as e:
        print(f"[companion] danmaku loop failed: {e}")
    # 启动 job schedule：注入业务单例并恢复任务
    try:
        job_manager.build(
            memory=memory,
            tool_registry=tool_registry,
            skill_registry=skill_registry,
            symbix_client=symbix_client,
            provider_registry=provider_registry,
            checkpoint_recorder=checkpoint_recorder,
            pet_action=pet_action,
        )
        job_manager.start()
        jobs._set_manager(job_manager)
        print("[job] JobScheduler started")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[job] failed to start JobScheduler: {e}")
    yield
    _force_close_sse("lifespan")
    try:
        if _danmaku_task:
            _danmaku_task.cancel()
    except Exception:
        pass
    try:
        job_manager.shutdown()
        print("[job] JobScheduler stopped")
    except Exception as e:
        print(f"[job] shutdown failed: {e}")
    try:
        mcp_manager.stop_all()
        print("[MCP] All servers stopped")
    except Exception as e:
        print(f"[MCP] stop_all failed: {e}")


# ============ FastAPI App ============
app = FastAPI(title="Symbix API", version="0.1.0", lifespan=lifespan)

# ============ CORS 跨域支持 ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ 挂载路由 ============
app.include_router(chat.router)
app.include_router(providers.router)
app.include_router(mcp.router)
app.include_router(skills.router)
app.include_router(sessions.router)
app.include_router(pet.router)
app.include_router(files.router)
app.include_router(checkpoint.router)
app.include_router(risk.router)
app.include_router(jobs.router)
app.include_router(voice.router)
app.include_router(journal.router)
app.include_router(danmaku.router)


@app.get("/")
async def root():
    """根路径 - API 状态检查"""
    return {
        "status": "ok",
        "service": "Symbix API",
        "version": "0.1.0",
    }


# ============ 启动入口 ============
if __name__ == "__main__":
    use_reload = "--reload" in sys.argv
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=use_reload,
        log_level="info",
        # Windows + reload 下 uvicorn 默认强制 SelectorEventLoop,会导致
        # STT(SenseVoice 子进程)启动失败(create_subprocess_exec 不支持)。
        # 用自定义 loop factory 强制 ProactorEventLoop,让热重载与 STT 共存。
        loop="loop_proactor:force_proactor",
        # 即使仍有顽固连接,最多等 1s 后强制结束,避免卡死开发流程
        timeout_graceful_shutdown=1,
        timeout_keep_alive=5,
    )
