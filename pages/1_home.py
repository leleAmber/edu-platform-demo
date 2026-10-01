"""首页：欢迎区、单元选择、功能入口卡片、今日学习建议、最近学习记录。"""

from __future__ import annotations

import streamlit as st

from components.cards import func_card, status_tag
from core import auth, database, tutor_ai, vip

PAGE_PREVIEW = "pages/2_preview.py"
PAGE_REVIEW = "pages/3_review.py"
PAGE_HOMEWORK = "pages/4_homework.py"
PAGE_EXAM = "pages/5_mock_exam.py"
PAGE_MEMBER = "pages/6_membership.py"
PAGE_ADMIN = "pages/8_admin.py"

DAILY_TIPS = (
    "先花 10 分钟朗读课文，再开始做题，语感会明显提升。",
    "错题不要只看答案，写下错因才能真正记住。",
    "每天背 5 个新词并各造 1 个句子，一周就是 35 个。",
)

user = auth.require_login()


def render_member_status() -> None:
    if vip.is_vip(user):
        status_tag("👑 VIP 会员", "vip")
        st.caption(f"有效期至 {vip.vip_until_text(user)}")
    else:
        status_tag("免费版", "plain")
        st.caption("开通会员可解锁模拟试卷与学情诊断")


# --------------------------------------------------------------------------- #
# 学生首页
# --------------------------------------------------------------------------- #
def render_student_home() -> None:
    col_welcome, col_status = st.columns([3, 1], vertical_alignment="center")
    with col_welcome:
        st.subheader(f"👋 欢迎回来，{user['username']}")
        st.caption("选好单元，从预习、复习到作业批改，一步步把课本学透。")
    with col_status:
        render_member_status()

    st.divider()

    st.selectbox(
        "选择学习单元",
        tutor_ai.UNITS,
        key="current_unit",
        help="这里选择的单元会在预习、复习、学情诊断页面中同步生效",
    )
    unit = st.session_state["current_unit"]
    st.caption(f"当前单元主题：{tutor_ai.get_unit_content(unit)['theme']}")

    st.subheader("学习功能")
    columns = st.columns(4)
    with columns[0]:
        func_card("课本预习", "课文导读、AI 长难句解析、核心词汇，先人一步。", PAGE_PREVIEW, icon="📖")
    with columns[1]:
        func_card("课本复习", "单元知识点总览与练习，把学过的内容真正记住。", PAGE_REVIEW, icon="🔄")
    with columns[2]:
        func_card("作业中心", "粘贴作文或课后习题，AI 逐句批改并给出修改建议。", PAGE_HOMEWORK, icon="✍️")
    with columns[3]:
        func_card("模拟试卷", "阅读、语言运用、书面写作三大板块综合演练。", PAGE_EXAM,
                  icon="📝", tag=("VIP", "vip"))

    st.subheader("今日学习建议")
    with st.container(border=True):
        for index, tip in enumerate(DAILY_TIPS, 1):
            st.markdown(f"**{index}.** {tip}")

    st.subheader("最近学习记录")
    records = database.get_learning_records(user["username"])
    if not records:
        st.info("还没有学习记录，先去「课本预习」完成一次练习吧。")
    else:
        rows = [
            {
                "时间": record.get("time", ""),
                "学习模块": record.get("module", ""),
                "单元": record.get("unit", ""),
                "得分": record.get("score", ""),
                "评级": record.get("level", ""),
            }
            for record in records[:5]
        ]
        st.dataframe(rows, width="stretch", hide_index=True)


# --------------------------------------------------------------------------- #
# 管理员首页
# --------------------------------------------------------------------------- #
def render_admin_home() -> None:
    col_welcome, col_status = st.columns([3, 1], vertical_alignment="center")
    with col_welcome:
        st.subheader(f"👋 欢迎回来，{user['username']}")
        st.caption("这里是课伴AI 管理后台，可查看用户、订单与客服留言。")
    with col_status:
        status_tag("管理员", "info")

    st.divider()

    users = database.get_all_users()
    orders = database.get_all_orders()
    messages = database.get_all_messages()

    col_users, col_students, col_orders, col_income = st.columns(4)
    col_users.metric("注册用户数", len(users))
    col_students.metric("学生账号", sum(1 for item in users if item.get("role") == "student"))
    col_orders.metric("会员订单数", len(orders))
    col_income.metric("累计收入", f"¥{sum(float(item.get('amount', 0)) for item in orders):.0f}")

    col_pending, _, _, _ = st.columns(4)
    col_pending.metric("待回复留言", sum(1 for item in messages if not item.get("is_replied")))

    st.subheader("管理功能")
    columns = st.columns(3)
    with columns[0]:
        func_card("用户管理", "按用户名或邮箱搜索用户，查看角色与会员状态。",
                  PAGE_ADMIN, icon="👥", key="admin_card_users",
                  state={"_pending_admin_tab": "用户管理"})
    with columns[1]:
        func_card("消费记录", "统计订单数量与累计收入，查看每笔开通明细。",
                  PAGE_ADMIN, icon="🧾", key="admin_card_orders",
                  state={"_pending_admin_tab": "消费记录"})
    with columns[2]:
        func_card("客服留言", "查看学生留言并逐条回复，标记处理状态。",
                  PAGE_ADMIN, icon="💬", key="admin_card_messages",
                  state={"_pending_admin_tab": "客服留言"})


st.title("🏠 首页")

if user.get("role") == "admin":
    render_admin_home()
else:
    render_student_home()
