"""FastAPI 应用入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core import database  # noqa: E402  —— app/__init__ 已 bootstrap，可直接导入

from . import config  # noqa: E402
from .middleware import RuntimeContextMiddleware  # noqa: E402
from .routers import (  # noqa: E402
    admin,
    diagnosis,
    homework,
    job,
    membership,
    messages,
    mock_exam,
    quiz,
    session,
    textbook,
)

logger = logging.getLogger("keban-api")

app = FastAPI(
    title="课伴AI · 移动端 API",
    description="英语课本智能学习助手的小程序后端。业务逻辑复用网页版 core/，同一份代码。",
    version="1.0.0",
    docs_url="/docs",
)

# CORS：小程序请求不带 Origin，用不上；主要是给 H5 版本和本地调试用
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 顺序很关键：先挂 CORS，再挂运行时上下文中间件。
# Starlette 的中间件是「后添加的先执行」，所以 RuntimeContext 在外层，
# 未登录请求也能被 CORS 正确封装。
app.add_middleware(RuntimeContextMiddleware)

for module in (session, textbook, quiz, homework, mock_exam, diagnosis,
               membership, messages, job, admin):
    app.include_router(module.router)


@app.on_event("startup")
def on_startup() -> None:
    """启动自检：连不上数据库就大声报错，别等到第一个请求才炸。"""
    ok, message = database.health_check()
    if ok:
        logger.info("数据库连接正常：%s", message)
    else:
        # 不直接退出：容器编排下反复重启更难排查，留 /health 给监控用
        logger.error("数据库连接失败：%s", message)


@app.get("/health", tags=["运维"], summary="健康检查")
def health() -> JSONResponse:
    ok, message = database.health_check()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"ok": ok, "database": message},
    )


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """兜底异常处理：不把堆栈暴露给客户端。"""
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )
