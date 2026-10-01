"""components：可复用 UI 组件层。

除 cards / charts / user_menu 三个组件模块外，这里放两个所有页面都会用到的
小工具：flash（跨 rerun 的提示队列）与 pending inputs（跨 rerun 回填输入框）。
"""

from __future__ import annotations

import streamlit as st

# 登录页需要隐藏侧边栏（Streamlit 原生侧边栏隐藏方式，仅此一处样式）
HIDE_SIDEBAR_CSS = """<style>[data-testid="stSidebar"]{display: none;}</style>"""

_FLASH_KEY = "_flash_queue"
_PENDING_KEY = "_pending_inputs"


def flash(message: str, icon: str | None = None) -> None:
    """登记一条提示，在下一次页面刷新时用 st.toast 弹出。

    st.toast 在 st.rerun() 之后会丢失，所以先入队、重跑后再弹。
    """
    st.session_state.setdefault(_FLASH_KEY, []).append({"message": message, "icon": icon})


def show_flash() -> None:
    """弹出所有已登记的提示，由 app.py 在每次运行开头调用。"""
    queue = st.session_state.pop(_FLASH_KEY, [])
    for item in queue:
        st.toast(item["message"], icon=item.get("icon"))


def set_pending_inputs(mapping: dict) -> None:
    """登记要在下一次 rerun 回填的输入框值（例如自动填入验证码）。"""
    st.session_state[_PENDING_KEY] = dict(mapping)


def apply_pending_inputs() -> None:
    """把待回填的值写进 session_state，由 app.py 在最开头调用。

    必须在任何 widget 实例化之前执行，否则会被 Streamlit 判定为非法修改。
    """
    pending = st.session_state.pop(_PENDING_KEY, None)
    if not pending:
        return
    for key, value in pending.items():
        st.session_state[key] = value
