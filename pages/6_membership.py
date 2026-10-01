"""会员中心：套餐展示、模拟支付、权益对比。"""

from __future__ import annotations

import streamlit as st

from components import flash
from components.cards import status_tag
from core import auth, vip

user = auth.require_login()
st.title("👑 会员中心")
st.caption("开通会员即可解锁模拟试卷、学情诊断与作业逐句批改等全部学习能力。")


@st.dialog("确认订单", width="small")
def confirm_order_dialog(plan_name: str) -> None:
    plan = vip.PLANS[plan_name]
    st.markdown(f"**套餐名称**：{plan['name']}")
    st.markdown(f"**支付金额**：¥{plan['price']}")
    st.markdown(f"**会员有效期**：{plan['days']} 天")
    st.caption("演示环境为模拟支付，不会产生真实扣款。")

    col_cancel, col_pay = st.columns(2)
    if col_cancel.button("取消", key="order_cancel", width="stretch"):
        st.rerun(scope="app")
    if col_pay.button("确认支付", type="primary", key="order_pay", width="stretch"):
        result = vip.process_payment(user["username"], plan_name)
        if result["ok"]:
            flash("支付成功！会员已生效", icon="🎉")
            st.rerun(scope="app")
        else:
            st.toast(result["message"], icon="⚠️")


# --------------------------------------------------------------------------- #
# 当前会员状态
# --------------------------------------------------------------------------- #
with st.container(border=True):
    col_info, col_status = st.columns([3, 1], vertical_alignment="center")
    with col_info:
        st.markdown(f"**当前账号**：{user['username']}")
        if vip.is_vip(user):
            st.markdown(f"**会员状态**：已开通（{user.get('vip_plan') or '会员'}）")
            st.caption(f"到期时间：{vip.vip_until_text(user)}　｜　续费可顺延剩余天数")
        else:
            st.markdown("**会员状态**：暂未开通")
            st.caption("开通后即可使用模拟试卷、学情诊断等 VIP 专属功能。")
    with col_status:
        if vip.is_vip(user):
            status_tag("👑 VIP 会员", "vip")
        else:
            status_tag("免费版", "plain")

# --------------------------------------------------------------------------- #
# 套餐卡片
# --------------------------------------------------------------------------- #
st.subheader("选择套餐")
plan_columns = st.columns(3)
for index, plan_name in enumerate(vip.PLAN_ORDER):
    plan = vip.PLANS[plan_name]
    with plan_columns[index]:
        with st.container(border=True):
            col_name, col_tag = st.columns([2, 1], vertical_alignment="center")
            col_name.markdown(f"**{plan['name']}**")
            with col_tag:
                if plan["recommended"]:
                    status_tag("推荐", "vip")
                else:
                    status_tag("可选", "plain")

            st.markdown(f"### ¥{plan['price']}")
            st.caption(f"有效期 {plan['days']} 天")
            for benefit in plan["benefits"]:
                st.markdown(f"- {benefit}")

            if st.button(
                "立即开通",
                key=f"buy_{plan['name']}",
                type="primary" if plan["recommended"] else "secondary",
                width="stretch",
            ):
                confirm_order_dialog(plan["name"])

# --------------------------------------------------------------------------- #
# 权益对比
# --------------------------------------------------------------------------- #
st.subheader("权益对比")
comparison_rows = [
    {
        "功能权益": name,
        "免费版": "✅ 可用" if free else "— 未开放",
        "VIP 会员": "✅ 可用" if paid else "— 未开放",
    }
    for name, free, paid in vip.FEATURE_MATRIX
]
st.dataframe(comparison_rows, width="stretch", hide_index=True)

if not vip.is_vip(user):
    st.caption("提示：开通后返回「模拟试卷」「学情诊断」即可立即使用。")
