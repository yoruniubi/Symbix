"""对话路由包:拆分自原 chat.py(1964 行),按职责分为 5 个子模块。

- helpers.py   : 共享辅助(交互工具判定 / SSE 批处理 / checkpoint 发射 / 消息构建)
- files_api.py : /upload, /parse_file
- approve.py   : /chat/approve
- stream.py    : /chat/stream, /history

对外保持 `from application.routers import chat; chat.router` 兼容。
注意:原 nonstream.py(`POST /chat` 非流端点)已于 2026-09-20 废弃删除——
前端只用 SSE 流式(/chat/stream)与审批续跑(/chat/approve),非流路径无调用方,
避免三处生成逻辑行为漂移。删除后可从 git 历史还原(dd5680c 拆包后文件)。
"""
from fastapi import APIRouter

from application.routers.chat.files_api import router as _files_router
from application.routers.chat.approve import router as _approve_router
from application.routers.chat.stream import router as _stream_router

router = APIRouter(tags=["chat"])
router.include_router(_files_router)
router.include_router(_approve_router)
router.include_router(_stream_router)

__all__ = ["router"]