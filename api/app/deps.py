"""鉴权依赖。

用户由 middleware.RuntimeContextMiddleware 绑定在请求上下文里，这里只做读取与
放行判断。同步依赖跑在线程池，但 ContextVar 是「复制进线程」的——读得到，
所以这里不写 ContextVar，只读。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from core import runtime, vip  # noqa: E402


def current_user() -> dict:
    """取当前登录用户；未登录抛 401。"""
    user = runtime.current_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_vip(user: dict = Depends(current_user)) -> dict:
    """VIP 专属接口。

    网页版是弹窗拦截（vip.check_vip_permission），API 版对应 403 —— 客户端据此
    展示「开通会员」引导页。判定逻辑复用 core.vip.is_vip，两边规则不会分叉。
    """
    if not vip.is_vip(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该功能为 VIP 专属，开通会员后即可使用",
        )
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    """管理员接口。"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
