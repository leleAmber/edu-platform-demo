"""运行时适配层：让 core/ 同一份代码同时服务 Streamlit 网页版与 FastAPI 后端。

存在的原因：core/auth 与 core/tutor_ai 直接读写 st.session_state。网页版下这没问题，
但在 FastAPI 进程里没有 Streamlit 运行时，tutor_ai._session_store() 会落到模块级
_FALLBACK_STORE —— 那是整个进程共享的字典，于是「A 用户抽的模拟卷被 B 用户判分」。
本模块把「当前是谁」与「他的会话数据」收敛到唯一入口，两种运行时行为各自正确：

- Streamlit 模式：透传 st.session_state / st.secrets，网页版行为与改造前完全一致；
- API 模式：请求级 ContextVar 绑定当前用户，会话缓存按用户隔离，配置读环境变量。

调用方一律不要自己判断运行时，只用 session_store() / current_user() / secret()。
"""

from __future__ import annotations

import os
import threading
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar

# --------------------------------------------------------------------------- #
# 运行时模式
# --------------------------------------------------------------------------- #
_MODE_BARE = "bare"            # 离线脚本：无 Streamlit 运行时，也无请求上下文
_MODE_STREAMLIT = "streamlit"
_MODE_API = "api"

_MODE: ContextVar[str] = ContextVar("keban_runtime_mode", default="")
_CURRENT_USER: ContextVar[dict | None] = ContextVar("keban_current_user", default=None)


def _detect_mode() -> str:
    """没有显式绑定模式时，探测当前进程跑在哪种运行时下。"""
    try:
        from streamlit import runtime  # 局部导入：API 进程里 streamlit 可能没装

        if runtime.exists():
            return _MODE_STREAMLIT
    except Exception:
        pass
    return _MODE_BARE


def current_mode() -> str:
    return _MODE.get() or _detect_mode()


def in_streamlit() -> bool:
    return current_mode() == _MODE_STREAMLIT


def in_api() -> bool:
    return current_mode() == _MODE_API


# --------------------------------------------------------------------------- #
# API 模式的用户会话缓存
# --------------------------------------------------------------------------- #
# 等价于网页版的 st.session_state：每个登录用户一份，互不可见。
# 键是用户名（登录后唯一且不可变）。用 LRU 封顶，防止长期运行内存无界增长。
_USER_STORES: OrderedDict[str, dict] = OrderedDict()
_USER_STORES_LOCK = threading.Lock()
_MAX_USER_STORES = 512

# 无请求上下文时的兜底容器（离线脚本用）。脚本单进程单用户跑一次，不存在串号问题；
# API 路径永远不会走到这里——api_request() 保证了上下文一定存在。
_BARE_STORE: dict = {}

# 请求级临时存储：未登录请求（如注册、登录前）用它，请求结束即销毁，绝不跨请求复用。
_REQUEST_STORE: ContextVar[dict | None] = ContextVar("keban_request_store", default=None)


def _user_store(username: str) -> dict:
    with _USER_STORES_LOCK:
        store = _USER_STORES.get(username)
        if store is None:
            store = {}
            _USER_STORES[username] = store
        _USER_STORES.move_to_end(username)
        while len(_USER_STORES) > _MAX_USER_STORES:
            _USER_STORES.popitem(last=False)
        return store


def clear_user_store(username: str) -> None:
    """清理某用户的会话缓存，登出时调用。"""
    with _USER_STORES_LOCK:
        _USER_STORES.pop(username, None)


# --------------------------------------------------------------------------- #
# 会话存储
# --------------------------------------------------------------------------- #
def session_store() -> dict:
    """当前用户的会话级缓存容器（等同 st.session_state 的语义）。

    API 模式下返回的是「按用户隔离」的字典，因此 tutor_ai 的练习/试卷缓存
    不会跨用户串数据 —— 这正是 _FALLBACK_STORE 之前的缺陷。
    """
    mode = current_mode()
    if mode == _MODE_STREAMLIT:
        import streamlit as st

        return st.session_state
    if mode == _MODE_API:
        user = _CURRENT_USER.get()
        if user and user.get("username"):
            return _user_store(str(user["username"]))
        # 未登录请求：请求级临时容器，随请求销毁
        store = _REQUEST_STORE.get()
        if store is None:
            store = {}
            _REQUEST_STORE.set(store)
        return store
    return _BARE_STORE


# --------------------------------------------------------------------------- #
# 当前用户
# --------------------------------------------------------------------------- #
def current_user() -> dict | None:
    mode = current_mode()
    if mode == _MODE_STREAMLIT:
        import streamlit as st

        user = st.session_state.get("current_user")
        return dict(user) if user else None
    if mode == _MODE_API:
        return _CURRENT_USER.get()
    return None


def set_current_user(user: dict | None) -> None:
    """写入当前用户。Streamlit 模式写 session_state；API 模式只更新 ContextVar
    （真正的持久化由调用方负责——API 用 JWT，不需要服务端会话）。"""
    mode = current_mode()
    if mode == _MODE_STREAMLIT:
        import streamlit as st

        if user is None:
            st.session_state.pop("current_user", None)
        else:
            st.session_state["current_user"] = dict(user)
        return
    if mode == _MODE_API:
        _CURRENT_USER.set(user)


@contextmanager
def api_request(user: dict | None = None):
    """FastAPI 依赖里包住整个请求：绑定模式与当前用户，退出时复位。

    ContextVar 会随 anyio 的线程池调用一起传递，所以同步的 core/ 函数
    （含 requests 调用）在 worker 线程里依然读得到正确的用户。
    """
    mode_token = _MODE.set(_MODE_API)
    user_token = _CURRENT_USER.set(user)
    store_token = _REQUEST_STORE.set(None)
    try:
        yield
    finally:
        _REQUEST_STORE.reset(store_token)
        _CURRENT_USER.reset(user_token)
        _MODE.reset(mode_token)


# --------------------------------------------------------------------------- #
# 配置读取
# --------------------------------------------------------------------------- #
def secret(name: str, default: str = "") -> str:
    """读配置：环境变量优先，回落 st.secrets（与 database._setting 一致）。

    网页版靠 .streamlit/secrets.toml；API 进程启动时把同一份 toml 注入环境变量，
    两条路读到的值一致，不需要维护两份配置。
    """
    value = os.environ.get(name)
    if value not in (None, ""):
        return str(value)
    try:
        import streamlit as st

        return str(st.secrets.get(name, default))
    except Exception:
        return default
