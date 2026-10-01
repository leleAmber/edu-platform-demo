"""侧边栏用户信息卡片组件：用户名、角色、会员状态标签、退出登录。"""

from __future__ import annotations

import streamlit as st

from components.cards import status_tag
from core import auth, vip

ROLE_LABELS = {"student": "学生", "admin": "管理员"}


def render_sidebar_user() -> None:
    """在侧边栏顶部渲染用户卡片；未登录时不渲染。"""
    user = auth.get_current_user()
    if not user:
        return

    with st.sidebar:
        with st.container(border=True):
            st.markdown(f"**👤 {user.get('username', '')}**")
            st.caption(f"角色：{ROLE_LABELS.get(user.get('role'), '学生')}")

            if vip.is_vip(user):
                status_tag("👑 VIP 会员", "vip")
                st.caption(f"有效期至 {vip.vip_until_text(user)}")
            else:
                status_tag("免费版", "plain")
                st.caption("开通会员解锁全部学习能力")

            if st.button("退出登录", key="sidebar_logout", use_container_width=True):
                auth.logout()
                st.rerun()
