"""教材选择器：7 册教材选一本作为「当前教材」，切换时把单元重置为该册首单元。

选书是前置逻辑——预习/复习/模拟卷都只围绕当前教材展开。选择结果存
st.session_state["current_book"]，单元存 st.session_state["current_unit"]。
"""

from __future__ import annotations

import streamlit as st

from core import textbook, tutor_ai


def _label(key: str) -> str:
    meta = textbook.get_book_meta(key)
    name = (meta or {}).get("name") or key
    return f"{key}｜{name}"


def render_book_selector() -> str:
    """渲染教材选择下拉框，返回当前选中的教材 key。"""
    keys = textbook.get_book_keys()
    if not keys:
        st.warning("未找到教材内容数据（data/textbooks/ 为空），请先运行 scripts/extract_textbooks.py。")
        return ""

    current = st.session_state.get("current_book")
    if current not in keys:
        current = keys[0]
        st.session_state["current_book"] = current

    chosen = st.selectbox(
        "选择教材",
        keys,
        index=keys.index(current),
        format_func=_label,
        key="book_selector_widget",
        help="选书后，课本预习 / 课本复习 / 模拟试卷的内容都只来自这一册教材",
    )

    # 教材变化时，把单元重置为新书首单元（避免跨书残留旧单元）
    if chosen != current:
        st.session_state["current_book"] = chosen
        units = tutor_ai.get_units(chosen)
        st.session_state["current_unit"] = units[0] if units else ""

    return st.session_state["current_book"]


def render_selectors() -> tuple[str, str]:
    """渲染「教材 + 单元」两级选择器，返回 (book, unit)。"""
    book = render_book_selector()
    units = tutor_ai.get_units(book)

    current = st.session_state.get("current_unit")
    if current not in units:
        current = units[0] if units else ""
        st.session_state["current_unit"] = current

    unit = current
    if units:
        unit = st.selectbox(
            "选择学习单元",
            units,
            index=units.index(current),
            key="current_unit",
            help="该单元会在预习、复习、学情诊断页面中同步生效",
        )
    return book, unit
