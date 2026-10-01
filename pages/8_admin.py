"""管理后台：用户管理、消费记录、客服留言（仅管理员可见）。"""

from __future__ import annotations

import streamlit as st

from components import flash
from components.cards import status_tag
from core import auth, database, vip

ROLE_LABELS = {"student": "学生", "admin": "管理员"}

user = auth.require_login()

# 角色校验：非管理员直接终止页面渲染
if user.get("role") != "admin":
    st.error("无权限访问管理后台")
    st.stop()

st.title("⚙️ 管理后台")
st.caption("管理注册用户、查看会员消费记录、回复学生留言。")


@st.dialog("回复留言", width="small")
def reply_dialog(msg_id: str, username: str, content: str) -> None:
    st.caption(f"来自 {username}：{content}")
    st.text_area("回复内容", key=f"reply_text_{msg_id}", height=140, placeholder="请输入回复内容")
    if st.button("提交回复", type="primary", key=f"reply_submit_{msg_id}", width="stretch"):
        reply_text = (st.session_state.get(f"reply_text_{msg_id}") or "").strip()
        if not reply_text:
            st.toast("请输入回复内容", icon="⚠️")
            return
        database.update_message(msg_id, reply_text)
        flash(f"已回复留言 {msg_id}", icon="✅")
        st.rerun(scope="app")


tab_users, tab_orders, tab_messages = st.tabs(
    ["用户管理", "消费记录", "客服留言"],
    default=st.session_state.get("admin_active_tab", "用户管理"),
    key="admin_active_tab",
)

# --------------------------------------------------------------------------- #
# Tab1 用户管理
# --------------------------------------------------------------------------- #
with tab_users:
    keyword = st.text_input(
        "搜索用户", key="admin_user_search", placeholder="输入用户名或邮箱进行搜索"
    )

    users = database.get_all_users()
    if keyword.strip():
        lowered = keyword.strip().lower()
        users = [
            item
            for item in users
            if lowered in str(item.get("username", "")).lower()
            or lowered in str(item.get("email", "")).lower()
        ]

    if not users:
        st.info("没有找到匹配的用户。")
    else:
        user_rows = [
            {
                "用户名": item.get("username", ""),
                "邮箱": item.get("email", ""),
                "角色": ROLE_LABELS.get(item.get("role"), "学生"),
                "VIP到期时间": vip.vip_until_text(item) if vip.is_vip(item) else "暂未开通",
                "注册时间": item.get("created_at", ""),
            }
            for item in users
        ]
        st.dataframe(user_rows, width="stretch", hide_index=True)
        st.caption(f"共 {len(user_rows)} 条记录")

# --------------------------------------------------------------------------- #
# Tab2 消费记录
# --------------------------------------------------------------------------- #
with tab_orders:
    orders = database.get_all_orders()
    total_income = sum(float(item.get("amount", 0)) for item in orders)
    paid_count = sum(1 for item in orders if item.get("status") == "已支付")

    col_count, col_income, col_paid = st.columns(3)
    col_count.metric("总订单数量", len(orders), border=True)
    col_income.metric("累计总收入", f"¥{total_income:.2f}", border=True)
    col_paid.metric("已支付订单", paid_count, border=True)

    if not orders:
        st.info("还没有会员订单记录。")
    else:
        order_rows = [
            {
                "订单号": item.get("order_id", ""),
                "用户名": item.get("username", ""),
                "套餐": item.get("plan_name", ""),
                "金额": f"¥{float(item.get('amount', 0)):.2f}",
                "有效天数": item.get("days", ""),
                "会员到期时间": item.get("vip_until", ""),
                "状态": item.get("status", ""),
                "下单时间": item.get("created_at", ""),
            }
            for item in orders
        ]
        st.dataframe(order_rows, width="stretch", hide_index=True)

# --------------------------------------------------------------------------- #
# Tab3 客服留言
# --------------------------------------------------------------------------- #
with tab_messages:
    messages = database.get_all_messages()
    pending_count = sum(1 for item in messages if not item.get("is_replied"))

    col_total_msg, col_pending_msg = st.columns(2)
    col_total_msg.metric("留言总数", len(messages), border=True)
    col_pending_msg.metric("待回复留言", pending_count, border=True)

    if not messages:
        st.info("还没有学生留言。")
    else:
        message_rows = [
            {
                "留言ID": item.get("msg_id", ""),
                "用户名": item.get("username", ""),
                "留言内容": item.get("content", ""),
                "提交时间": item.get("created_at", ""),
                "是否已回复": "已回复" if item.get("is_replied") else "待回复",
            }
            for item in messages
        ]
        st.dataframe(message_rows, width="stretch", hide_index=True)

        st.subheader("留言处理")
        for message in messages:
            with st.container(border=True):
                col_body, col_action = st.columns([3, 1])
                with col_body:
                    st.markdown(f"**{message.get('msg_id')}｜{message.get('username')}**")
                    st.write(message.get("content", ""))
                    st.caption(f"提交时间：{message.get('created_at', '')}")
                    if message.get("is_replied"):
                        st.markdown(f"**管理员回复**：{message.get('reply', '')}")
                        st.caption(f"回复时间：{message.get('replied_at', '')}")
                with col_action:
                    if message.get("is_replied"):
                        status_tag("已回复", "success")
                    else:
                        status_tag("待回复", "warn")
                        if st.button("回复", key=f"reply_{message.get('msg_id')}", width="stretch"):
                            reply_dialog(
                                message.get("msg_id", ""),
                                message.get("username", ""),
                                message.get("content", ""),
                            )
