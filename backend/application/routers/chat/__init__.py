"""对话路由包:拆分自原 chat.py(1964 行),按职责分为 5 个子模块。

- helpers.py   : 共享辅助(交互工具判定 / SSE 批处理 / checkpoint 发射 / 消息构建)
- files_api.py : /upload, /parse_file
- nonstream.py : /chat
- approve.py   : /chat/approve
- stream.py    : /chat/stream, /history

对外保持 `from application.routers import chat; chat.router` 兼容。
"""
from fastapi import APIRouter

from application.routers.chat.files_api import router as _files_router
from application.routers.chat.nonstream import router as _nonstream_router
from application.routers.chat.approve import router as _approve_router
from application.routers.chat.stream import router as _stream_router

router = APIRouter(tags=["chat"])
router.include_router(_files_router)
router.include_router(_nonstream_router)
router.include_router(_approve_router)
router.include_router(_stream_router)

__all__ = ["router"]