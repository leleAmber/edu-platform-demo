"""登录态：无状态 JWT。

网页版把登录态放 st.session_state，API 版没有服务端会话，改成签发 token。
payload 只放不变的身份信息（用户名、id、角色），不放 vip_until——
会员到期时间会变，塞进 token 会导致续费后仍拿着旧 token 的用户被判定为非会员。
每次请求按 sub 回数据库取最新用户，代价是一次主键查询。
"""

from __future__ import annotations

import time

import jwt

from . import config

ALGORITHM = "HS256"

# token 里不放敏感字段，这里显式白名单，避免 update_user 加了新字段就被带出去
_TOKEN_CLAIMS = ("sub", "uid", "role")


class TokenError(Exception):
    """token 无效/过期。"""


def create_token(user: dict) -> tuple[str, int]:
    """签发 token，返回 (token, 过期时间戳)。"""
    secret = config.jwt_secret()
    if not secret:
        raise RuntimeError("未配置 API_JWT_SECRET（或 AUTH_OTP_SECRET），无法签发登录凭证")

    now = int(time.time())
    expires_at = now + config.token_ttl_hours() * 3600
    payload = {
        "sub": str(user.get("username", "")),
        "uid": user.get("id"),
        "role": str(user.get("role", "student")),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM), expires_at


def decode_token(token: str) -> dict:
    """校验并解析 token；失败抛 TokenError。"""
    secret = config.jwt_secret()
    if not secret:
        raise TokenError("服务端未配置签发密钥")
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("登录凭证无效") from exc

    if not payload.get("sub"):
        raise TokenError("登录凭证缺少用户标识")
    return payload


def bearer_from_scope(scope: dict) -> str | None:
    """从 ASGI scope 的请求头里取 Bearer token。"""
    for name, value in scope.get("headers") or ():
        if name == b"authorization":
            text = value.decode("latin-1").strip()
            if text[:7].lower() == "bearer ":
                return text[7:].strip()
            return None
    return None
