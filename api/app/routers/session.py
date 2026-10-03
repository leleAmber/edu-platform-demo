"""认证：邮箱验证码注册、账号密码登录、微信一键登录、当前用户、登出。

与网页版并存：同一张 users 表、同一套密码哈希与验证码规则（core.auth 复用）。
区别只是网页版把登录态写 session_state，这里签发 JWT。
"""

from __future__ import annotations

import os
import secrets

import requests
from fastapi import APIRouter, Depends, HTTPException, status

from core import auth, database, runtime  # noqa: E402

from ..deps import current_user  # noqa: E402
from ..schemas import (  # noqa: E402
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
    WechatLoginRequest,
)
from ..security import create_token  # noqa: E402
from ..serialize import user_payload  # noqa: E402

router = APIRouter(prefix="/auth", tags=["认证"])

WECHAT_CODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"


def _login_response(user: dict) -> dict:
    token, expires_at = create_token(user)
    return {"token": token, "expires_at": expires_at, "user": user_payload(user)}


@router.post("/send-code", summary="发送注册验证码")
def send_code(payload: SendCodeRequest) -> dict:
    ok, message, dev_code = auth.send_verification_code(payload.email)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    body = {"ok": True, "message": message}
    # 仅本地演示模式会返回验证码；生产环境该字段恒为 None，不会泄漏
    if dev_code:
        body["dev_code"] = dev_code
    return body


@router.post("/register", summary="注册并直接登录")
def register(payload: RegisterRequest) -> dict:
    ok, message = auth.register(
        payload.username,
        payload.email,
        payload.password,
        payload.confirm_password,
        payload.code,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    user = database.get_user_by_username(payload.username)
    if not user:
        raise HTTPException(status_code=500, detail="注册成功但读取用户失败，请直接登录")
    return _login_response(dict(user))


@router.post("/login", summary="账号密码登录")
def login(payload: LoginRequest) -> dict:
    if not auth.login(payload.username, payload.password):
        # 不区分「用户不存在」与「密码错误」，避免被用来枚举账号
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码不正确")
    user = runtime.current_user()
    if not user:
        raise HTTPException(status_code=500, detail="登录状态异常，请重试")
    return _login_response(dict(user))


@router.post("/wechat", summary="微信一键登录")
def wechat_login(payload: WechatLoginRequest) -> dict:
    """用 wx.login 的 code 换 openid；首次登录自动建号。

    未配置 WX_APPID / WX_SECRET 时返回 503 而不是静默失败，
    让客户端能明确提示「微信登录暂不可用，请用账号密码登录」。
    """
    appid = os.environ.get("WX_APPID", "").strip()
    secret = os.environ.get("WX_SECRET", "").strip()
    if not (appid and secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="微信登录未配置（缺少 WX_APPID / WX_SECRET），请使用账号密码登录",
        )

    try:
        resp = requests.get(
            WECHAT_CODE2SESSION,
            params={
                "appid": appid,
                "secret": secret,
                "js_code": payload.code,
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"调用微信接口失败：{exc}") from exc

    openid = data.get("openid")
    if not openid:
        # errcode 40029 = code 无效；45011 = 频率限制
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"微信登录失败：{data.get('errmsg') or '未获取到 openid'}",
        )

    user = database.get_user_by_openid(openid)
    if user is None:
        user = _create_wechat_user(openid)
    return _login_response(dict(user))


def _create_wechat_user(openid: str) -> dict:
    """微信首次登录建号。

    users 表的 email / password 都是 NOT NULL 且 email 唯一，微信用户两样都没有：
    - email 用 openid@wechat.local 占位（.local 是保留域，不会有真人注册撞车）；
    - password 写一段随机值，等于这个账号**无法**用密码登录——
      这是有意的，不能让占位密码变成可猜的登录后门。
    """
    username = _unique_username(f"wx_{openid[:10]}")
    user = database.add_new_user(
        {
            "username": username,
            "email": f"{openid}@wechat.local",
            "password": database.hash_password(secrets.token_urlsafe(32)),
            "role": "student",
            "vip_until": None,
            "openid": openid,
        }
    )
    if user is None:
        raise HTTPException(status_code=500, detail="创建微信账号失败，请稍后重试")
    return user


def _unique_username(base: str) -> str:
    """用户名唯一（users.username 有唯一索引），重名时加数字后缀。"""
    candidate = base[:20]
    for _ in range(20):
        if not database.get_user_by_username(candidate):
            return candidate
        candidate = f"{base[:16]}{secrets.randbelow(10000):04d}"
    return f"{base[:12]}{secrets.token_hex(4)}"[:20]


@router.get("/me", summary="当前登录用户")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user_payload(user)}


@router.post("/logout", summary="登出")
def logout(user: dict = Depends(current_user)) -> dict:
    """JWT 是无状态的，服务端只需丢弃该用户的会话缓存。

    客户端负责删除本地 token。这里清缓存是为了让「登出后重新登录」拿到
    全新的抽题/组卷结果，而不是上一次会话的残留。
    """
    auth.logout()
    return {"ok": True, "message": "已退出登录"}
