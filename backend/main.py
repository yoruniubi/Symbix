"""
Symbix Backend - FastAPI Server
入口文件：组装 app、挂载路由、启动 uvicorn。
业务逻辑已拆分到 application/ 包。
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from application.state import mcp_manager
from application.routers import chat, providers, mcp, skills, sessions

# ============ FastAPI App ============
app = FastAPI(title="Symbix API", version="0.1.0")

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
    try:
        uvicorn.run(
            "main:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            log_level="info",
        )
    finally:
        mcp_manager.stop_all()
        print("[MCP] All servers stopped")
