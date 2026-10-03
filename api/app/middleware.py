"""请求级运行时上下文。

为什么用纯 ASGI 中间件而不是 BaseHTTPMiddleware / Depends：
core/ 里的函数（error_analysis、_stable_seed 等）会在内部调 auth.get_current_user()，
所以「当前是谁」必须对 core 的内部调用也可见。而

- BaseHTTPMiddleware 会把下游丢进新的 task，ContextVar 写在这里传不下去；
- 同步的 Depends 依赖在线程池里执行，写进去的 ContextVar 同样传不回接口函数。

纯 ASGI 中间件直接 await self.app(...)，下游在同一个 task 内运行，
ContextVar 全程可见；anyio 把同步接口丢进线程池时也会复制上下文，
所以 core/ 里同步的 requests 调用一样读得到用户。
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from core import database, runtime  # noqa: E402  —— config.bootstrap() 已把 core 加进 sys.path

from . import security


def _load_user(username: str) -> dict | None:
    """按用户名回库取最新用户（放线程池执行，避免阻塞事件循环）。"""
    try:
        return database.get_user_by_username(username)
    except Exception:
        return None


class RuntimeContextMiddleware:
    """解析 Bearer token → 绑定请求级用户上下文 → 交给下游处理。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        user: dict | None = None
        token = security.bearer_from_scope(scope)
        if token:
            try:
                # 解码是纯计算（HMAC 校验），放事件循环里做开销可忽略
                payload = security.decode_token(token)
            except security.TokenError:
                payload = None
            if payload:
                # 回库取最新用户：会员到期、角色变更立即生效，不受 token 签发时间影响
                loaded = await run_in_threadpool(_load_user, payload["sub"])
                if loaded:
                    user = dict(loaded)

        # 关键：在同一个 task 内进入上下文，下游（含 core 内部调用）全程可见
        with runtime.api_request(user):
            await self.app(scope, receive, send)
