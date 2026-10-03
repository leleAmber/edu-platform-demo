"""认证层：注册（邮箱验证码）、登录、登出、会话用户。

验证码只保存 HMAC 摘要，10 分钟过期，同一邮箱 60 秒内只能发一次，最多校验 5 次。

存储分两种运行时（见 core/runtime.py）：
- 网页版：验证码与登录态都放 st.session_state，不落盘；
- API 版：登录态改为无状态（调用方签发 JWT），验证码必须落 otp_codes 表——
  注册是「发码」与「提交」两次独立 HTTP 请求，进程内存储活不过请求边界，
  不落库的话任何验证码都校验不过。
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import smtplib
import time
from email.message import EmailMessage

from core import database, runtime

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
CODE_TTL_SECONDS = 600          # 验证码有效期：10 分钟
SEND_INTERVAL_SECONDS = 60      # 同一邮箱发送间隔：60 秒
MAX_VERIFY_ATTEMPTS = 5         # 单个验证码最多校验次数
DEV_CODE = "123456"             # 本地演示模式固定验证码

# VIP 拦截弹窗的会话标记前缀，登出时统一清理
GATE_FLAG_PREFIX = "_vip_gate_shown_"

USERNAME_MIN, USERNAME_MAX = 2, 20
PASSWORD_MIN = 6

_OTP_STORE_KEY = "_otp_store"
_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


# --------------------------------------------------------------------------- #
# 配置读取
# --------------------------------------------------------------------------- #
def _secret(name: str, default: str = "") -> str:
    """读配置（环境变量优先，回落 secrets），缺文件或缺字段时返回默认值，不让应用崩溃。"""
    return runtime.secret(name, default)


def _is_dev_mode() -> bool:
    return _secret("AUTH_DEV_MODE", "0") == "1"


def get_smtp_config() -> dict | None:
    """组装 SMTP 配置；缺少关键字段时返回 None（走演示模式）。"""
    host = _secret("SMTP_HOST")
    login = _secret("SMTP_LOGIN")
    password = _secret("SMTP_PASSWORD")
    if not (host and login and password):
        return None
    sender = _secret("SMTP_SENDER_EMAIL") or login
    return {
        "host": host,
        "port": int(_secret("SMTP_PORT", "465") or 465),
        "use_ssl": _secret("SMTP_USE_SSL", "1") != "0",
        "login": login,
        "password": password,
        "sender": sender,
    }


# --------------------------------------------------------------------------- #
# 验证码存储
# --------------------------------------------------------------------------- #
class _SessionOTP:
    """网页版后端：验证码存当前会话，不落盘（原有行为）。"""

    @staticmethod
    def _store() -> dict:
        return runtime.session_store().setdefault(_OTP_STORE_KEY, {})

    def get(self, email: str) -> dict | None:
        return self._store().get(email)

    def set(self, email: str, record: dict) -> None:
        self._store()[email] = record

    def pop(self, email: str) -> dict | None:
        return self._store().pop(email, None)

    def bump_attempts(self, email: str) -> int:
        record = self._store().get(email)
        if record is None:
            return 0
        record["attempts"] = int(record.get("attempts", 0)) + 1
        return record["attempts"]


class _DatabaseOTP:
    """API 版后端：验证码落 otp_codes 表，重启与多进程都不丢。"""

    def get(self, email: str) -> dict | None:
        return database.get_otp(email)

    def set(self, email: str, record: dict) -> None:
        database.set_otp(email, record)

    def pop(self, email: str) -> dict | None:
        record = database.get_otp(email)
        database.clear_otp(email)
        return record

    def bump_attempts(self, email: str) -> int:
        return database.bump_otp_attempts(email)


def _otp() -> _SessionOTP | _DatabaseOTP:
    return _DatabaseOTP() if runtime.in_api() else _SessionOTP()


def _hash_code(email: str, code: str) -> str:
    secret = _secret("AUTH_OTP_SECRET") or "keban-ai-local-demo"
    message = f"{email.strip().lower()}:{code.strip()}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _send_email(to_email: str, code: str) -> None:
    """通过配置的 SMTP 发送验证码，失败时抛出异常由调用方处理。"""
    config = get_smtp_config()
    if not config:
        raise RuntimeError("未配置 SMTP 发件服务")

    message = EmailMessage()
    message["Subject"] = "课伴AI｜注册邮箱验证码"
    message["From"] = config["sender"]
    message["To"] = to_email
    message.set_content(
        f"你的注册验证码是：{code}\n\n"
        f"验证码 {CODE_TTL_SECONDS // 60} 分钟内有效，请勿转发给他人。\n"
        "如果这不是你本人的操作，忽略本邮件即可。"
    )

    if config["use_ssl"]:
        client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=15)
    else:
        client = smtplib.SMTP(config["host"], config["port"], timeout=15)
    with client:
        if not config["use_ssl"]:
            client.starttls()
        client.login(config["login"], config["password"])
        client.send_message(message)


def _short_error(exc: Exception) -> str:
    """把 SMTP 异常转成用户能看懂的一句话，避免把服务端细节整段抛出。"""
    text = str(exc).strip() or exc.__class__.__name__
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "发件邮箱认证失败，请检查 SMTP 授权码"
    if isinstance(exc, (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, OSError)):
        return "无法连接发件服务器，请检查网络或 SMTP 配置"
    return text[:80]


def send_verification_code(email: str) -> tuple[bool, str, str | None]:
    """发送注册验证码。

    返回 (是否成功, 提示文字, 演示验证码)。
    演示验证码仅在「本地演示模式」下返回，其余情况一律为 None——发送失败时只报错，
    绝不把验证码回传给调用方。
    """
    email = (email or "").strip().lower()
    if not _EMAIL_PATTERN.match(email):
        return False, "请输入正确的邮箱地址", None

    backend = _otp()
    record = backend.get(email)
    now = time.time()
    if record and now - record["sent_at"] < SEND_INTERVAL_SECONDS:
        wait = int(SEND_INTERVAL_SECONDS - (now - record["sent_at"])) + 1
        return False, f"发送太频繁了，请 {wait} 秒后再试", None

    dev_mode = _is_dev_mode()
    code = DEV_CODE if dev_mode else f"{secrets.randbelow(1_000_000):06d}"
    backend.set(email, {
        "hash": _hash_code(email, code),
        "sent_at": now,
        "expires_at": now + CODE_TTL_SECONDS,
        "attempts": 0,
        "dev_mode": dev_mode,
    })

    if dev_mode:
        return True, "本地演示模式：验证码已生成", DEV_CODE

    try:
        _send_email(email, code)
    except Exception as exc:  # noqa: BLE001 - 统一转成可读提示
        # 发送失败：作废本次验证码并只回报错误，绝不把验证码返回给调用方。
        # 同时清掉发送记录，让用户可以立即重试而不必等满 60 秒限流。
        backend.pop(email)
        return False, f"验证码发送失败：{_short_error(exc)}，请稍后重试", None

    return True, f"验证码已发送至 {email}，{CODE_TTL_SECONDS // 60} 分钟内有效", None


def verify_code(email: str, code: str) -> tuple[bool, str]:
    """校验验证码，成功后立即失效。返回 (是否通过, 提示文字)。"""
    email = (email or "").strip().lower()
    code = (code or "").strip()
    backend = _otp()
    record = backend.get(email)

    if not record:
        return False, "请先点击「获取验证码」"
    if time.time() > record["expires_at"]:
        backend.pop(email)
        return False, "验证码已过期，请重新获取"
    if record["attempts"] >= MAX_VERIFY_ATTEMPTS:
        backend.pop(email)
        return False, "验证码错误次数过多，请重新获取"
    if not hmac.compare_digest(record["hash"], _hash_code(email, code)):
        # 经 backend 累加：API 后端每次读的是数据库新行，就地把 record 改掉不会持久化
        attempts = backend.bump_attempts(email)
        left = max(0, MAX_VERIFY_ATTEMPTS - attempts)
        return False, f"验证码不正确，还可以尝试 {left} 次"

    backend.pop(email)
    return True, "验证成功"


# --------------------------------------------------------------------------- #
# 登录 / 注册 / 登出
# --------------------------------------------------------------------------- #
def login(username: str, password: str) -> bool:
    """校验账号密码，成功写入当前用户。

    网页版写入 st.session_state；API 版只设置请求级上下文，调用方需据此签发 JWT。
    """
    user = database.get_user_by_username(username)
    if not user or not database.verify_password(password, user.get("password", "")):
        return False
    runtime.set_current_user(dict(user))
    return True


def register(username: str, email: str, password: str, confirm_pwd: str, code: str) -> tuple[bool, str]:
    """注册校验：全部通过才写入用户表，返回 (是否成功, 提示文字)。"""
    username = (username or "").strip()
    email = (email or "").strip().lower()
    password = password or ""
    confirm_pwd = confirm_pwd or ""
    code = (code or "").strip()

    if not (USERNAME_MIN <= len(username) <= USERNAME_MAX):
        return False, f"用户名长度需为 {USERNAME_MIN}~{USERNAME_MAX} 个字符"
    if " " in username:
        return False, "用户名不能包含空格"
    if database.get_user_by_username(username):
        return False, "该用户名已被注册，换一个试试"
    if not _EMAIL_PATTERN.match(email):
        return False, "请输入正确的邮箱地址"
    if database.get_user_by_email(email):
        return False, "该邮箱已被注册，可直接登录或更换邮箱"
    if len(password) < PASSWORD_MIN:
        return False, f"密码至少 {PASSWORD_MIN} 位"
    if password != confirm_pwd:
        return False, "两次输入的密码不一致"
    if not code:
        return False, "请填写邮箱验证码"

    passed, message = verify_code(email, code)
    if not passed:
        return False, message

    created = database.add_new_user(
        {
            "username": username,
            "email": email,
            "password": database.hash_password(password),
            "role": "student",
            "vip_until": None,
        }
    )
    if created is None:
        return False, "注册失败，用户名可能已被占用"
    return True, "注册成功"


def logout() -> None:
    """清空登录态与相关的会话标记。"""
    # 必须趁登录态还在时取到会话容器：API 模式下清掉用户后 session_store() 就换了容器
    store = runtime.session_store()
    user = runtime.current_user()

    for key in list(store.keys()):
        if str(key).startswith(GATE_FLAG_PREFIX) or key == _OTP_STORE_KEY:
            store.pop(key, None)

    runtime.set_current_user(None)

    # API 模式下丢弃该用户的整份缓存（含抽题/组卷结果），下次登录重新开始
    if user and user.get("username"):
        runtime.clear_user_store(str(user["username"]))


def get_current_user() -> dict | None:
    """读取当前登录用户，未登录返回 None。"""
    return runtime.current_user()


def refresh_current_user() -> dict | None:
    """会员开通等场景下重新从数据表同步会话用户，保证界面立即更新。"""
    user = runtime.current_user()
    if not user:
        return None
    latest = database.get_user_by_username(user["username"])
    if latest:
        runtime.set_current_user(dict(latest))
        return dict(latest)
    return user


def require_login() -> dict:
    """页面级登录守卫（仅网页版）：未登录时中止渲染，避免直接输入 URL 绕过登录页。

    API 版用依赖注入做鉴权，不要调用本函数。
    """
    import streamlit as st

    user = get_current_user()
    if user is None:
        st.error("登录状态已失效，请返回首页重新登录。")
        st.stop()
    return user
