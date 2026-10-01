"""通用 UI 组件：功能入口卡片、单词知识点卡片、状态标签。"""

from __future__ import annotations

import streamlit as st

# 状态标签类型 → st.badge 颜色
_BADGE_COLORS = {
    "vip": "yellow",
    "success": "green",
    "warn": "orange",
    "danger": "red",
    "info": "blue",
    "plain": "gray",
}

# 状态标签类型 → markdown 文字颜色（老版本 Streamlit 的降级方案）
_MARKDOWN_COLORS = {
    "vip": "orange",
    "success": "green",
    "warn": "orange",
    "danger": "red",
    "info": "blue",
    "plain": "gray",
}


def status_tag(text: str, tag_type: str = "success") -> None:
    """状态标签，tag_type 可选 vip / success / warn / danger / info / plain。"""
    if hasattr(st, "badge"):
        st.badge(text, color=_BADGE_COLORS.get(tag_type, "gray"))
    else:
        st.markdown(f":{_MARKDOWN_COLORS.get(tag_type, 'gray')}[**{text}**]")


def func_card(
    title: str,
    desc: str,
    target_page: str,
    icon: str = "📘",
    tag: tuple[str, str] | None = None,
    key: str | None = None,
    state: dict | None = None,
) -> None:
    """功能入口卡片：标题 + 描述 + 跳转按钮。

    tag 为 (文字, 标签类型) 元组，例如 ("VIP", "vip")，会显示在卡片标题右侧；
    state 为跳转前要写入 session_state 的键值，用于指定目标页面的初始状态。
    """
    with st.container(border=True):
        if tag:
            col_title, col_tag = st.columns([2, 1], vertical_alignment="center")
            col_title.markdown(f"**{icon} {title}**")
            with col_tag:
                status_tag(tag[0], tag[1])
        else:
            st.markdown(f"**{icon} {title}**")
        st.caption(desc)
        if st.button("进入学习", key=key or f"func_card_{title}", width="stretch"):
            if state:
                st.session_state.update(state)
            goto_page(target_page)


def knowledge_card(word: str, pos: str, explain: str, sentence: str) -> None:
    """单词知识点卡片：单词、词性、中文释义、例句。"""
    with st.container(border=True):
        st.markdown(f"**{word}** `{pos}`")
        st.write(explain)
        st.caption(f"例句：{sentence}")


def goto_page(target_page: str) -> None:
    """跳转到指定页面；页面未注册时给出可操作的提示而不是直接报错。"""
    try:
        st.switch_page(target_page)
    except Exception:
        st.toast("请在左侧菜单中打开对应页面", icon="➡️")
