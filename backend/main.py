from contextlib import asynccontextmanager
import asyncio
import sys as _sys

# Windows 控制台默认 cp1252,中文日志(如「SDK 运行时目录已加入 PATH」)会
# UnicodeEncodeError 直接崩。必须在任何中文 print 之前统一兜底。
# 治本:所有启动日志/后续运行时日志一处修复全覆盖。
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

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
    memory_store,
)
import sys
import os
from application.routers import chat, providers, mcp, skills, sessions, pet, files, checkpoint, risk, jobs, voice, journal, danmaku, usage


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


def _ensure_first_run_files() -> None:
    """首次运行补齐可自建的配置文件。

    打包后 _MEIPASS 里只带了模板(providers.json.example),其它配置由代码自建;
    exec 白名单是唯一一个「写了生成函数但没人调用」的,这里补上 ——
    否则缺文件时白名单为空,auto 模式下所有命令都被拦。
    """
    try:
        from application.services.risk_context import ensure_exec_whitelist_exists
        ensure_exec_whitelist_exists()
    except Exception as e:
        print(f"[runtime] exec 白名单初始化失败: {e}")


def _log_frozen_paths() -> None:
    """冻结后把「数据落到哪」打出来,方便第一时间发现路径问题(开发态不打扰)。"""
    if not getattr(sys, "frozen", False):
        return
    try:
        from application.state import BASE_DIR
        from Symbix_sdk.resource_path import resource_root
        print(f"[runtime] frozen BASE_DIR = {BASE_DIR}")
        print(f"[runtime] resource_root() = {resource_root()}")
    except Exception as e:
        print(f"[runtime] 路径自检失败: {e}")


_ensure_bundled_runtime_on_path()
_ensure_first_run_files()
_log_frozen_paths()


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
                # 主动搭话:空闲 + 抖动 + 频控,可能携带记忆回访(详见 companion_proactive.py)
                from application.services.companion_proactive import _maybe_probe
                _maybe_probe()
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
        # 让 Agent 的定时任务工具也用同一个 manager(create/list/cancel_schedule_job)
        try:
            from Symbix_sdk.tools.builtin import job_tools
            job_tools.set_job_manager(job_manager)
        except Exception as _e:
            print(f"[job] 定时任务工具未能绑定 manager: {_e}")
        # 长期记忆工具(save_memory / search_memories)绑定同一个 MemoryStore
        try:
            from Symbix_sdk.tools.builtin import memory_tools
            memory_tools.set_memory_store(memory_store)
        except Exception as _e:
            print(f"[memory] 记忆工具未能绑定 store: {_e}")
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
        # 结束子进程树可能要几秒/个,丢线程池,别拖住关闭流程
        await asyncio.to_thread(mcp_manager.stop_all)
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
app.include_router(usage.router)


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
    # 端口:默认 8000;Tauri 侧会先挑一个空闲端口再用 SYMBIX_PORT 传进来
    # (传 0 = 让系统随便分一个,uvicorn 会把实际端口打进日志)。
    _port = int(os.environ.get("SYMBIX_PORT") or 8000)
    _uvicorn_kwargs = dict(
        host="127.0.0.1",
        port=_port,
        log_level="info",
        # Windows + reload 下 uvicorn 默认强制 SelectorEventLoop,会导致
        # STT(SenseVoice 子进程)启动失败(create_subprocess_exec 不支持)。
        # 用自定义 loop factory 强制 ProactorEventLoop,让热重载与 STT 共存。
        # 仅 win32:ProactorEventLoop 是 Windows 专有的,posix 上连这个属性都没有。
        **({"loop": "loop_proactor:force_proactor"} if sys.platform == "win32" else {}),
        # 即使仍有顽固连接,最多等 1s 后强制结束,避免卡死开发流程
        timeout_graceful_shutdown=1,
        timeout_keep_alive=5,
    )
    if getattr(sys, "frozen", False):
        # 打包(PyInstaller)后入口脚本不以 "main" 为模块名注册,`"main:app"` 这种
        # 字符串导入会报 No module named 'main';而把 main 加进 hiddenimports 又会
        # 让 state.py 二次执行(双份 DB 句柄 / 双份 MCP 线程)。所以冻结时直接传
        # app 对象,并关掉 reload(它要重启 exe,冻结后不适用)。
        uvicorn.run(app, **_uvicorn_kwargs)
    else:
        uvicorn.run("main:app", reload="--reload" in sys.argv, **_uvicorn_kwargs)
