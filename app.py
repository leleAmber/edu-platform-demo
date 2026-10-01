"""课伴AI｜英语课本智能学习助手 —— 应用入口。

本文件只负责三件事：
1. 全局初始化（session_state、提示队列、输入框回填）；
2. 未登录时的登录 / 注册页面渲染；
3. 已登录时按角色组装侧边导航，并把页面渲染交给 Streamlit 原生 pages 机制。

所有业务计算与数据读写都在 core/ 中完成，页面只做 UI 与交互。
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="课伴AI｜英语课本智能学习助手",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

from components import (  # noqa: E402  - 必须在 set_page_config 之后导入
    HIDE_SIDEBAR_CSS,
    apply_pending_inputs,
    flash,
    set_pending_inputs,
    show_flash,
)
from components import user_menu  # noqa: E402
from core import auth, database  # noqa: E402

# --------------------------------------------------------------------------- #
# 页面路径（与 pages/ 下的文件名一一对应）
# --------------------------------------------------------------------------- #
PAGE_HOME = "pages/1_home.py"
PAGE_PREVIEW = "pages/2_preview.py"
PAGE_REVIEW = "pages/3_review.py"
PAGE_HOMEWORK = "pages/4_homework.py"
PAGE_EXAM = "pages/5_mock_exam.py"
PAGE_MEMBER = "pages/6_membership.py"
PAGE_DIAGNOSIS = "pages/7_diagnosis.py"
PAGE_ADMIN = "pages/8_admin.py"

ADMIN_SECTIONS = ("用户管理", "消费记录", "客服留言")


# --------------------------------------------------------------------------- #
# 会话状态初始化
# --------------------------------------------------------------------------- #
def init_session_state() -> None:
    """初始化全局会话状态，页面切换时这些状态不会丢失。"""
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("current_unit", "Unit1 Teenage Life")
    st.session_state.setdefault("learning_records", [])
    st.session_state.setdefault("_current_page", None)


# --------------------------------------------------------------------------- #
# 登录 / 注册页面
# --------------------------------------------------------------------------- #
@st.dialog("忘记密码", width="small")
def _forgot_password_dialog() -> None:
    st.write("演示环境暂不支持找回密码，请使用演示账号 student / admin 登录。")
    st.caption("正式上线后可接入邮箱验证码重置密码流程。")
    if st.button("我知道了", type="primary", use_container_width=True, key="forgot_confirm"):
        st.rerun(scope="app")


def _apply_remembered_login() -> None:
    """把「记住密码」保存的账号回填到登录表单。"""
    remembered = st.session_state.get("remembered_login")
    if not remembered:
        return
    if "login_username" not in st.session_state:
        st.session_state["login_username"] = remembered.get("username", "")
    if "login_password" not in st.session_state:
        st.session_state["login_password"] = remembered.get("password", "")
    if "login_remember" not in st.session_state:
        st.session_state["login_remember"] = True


def _handle_login() -> None:
    username = (st.session_state.get("login_username") or "").strip()
    password = st.session_state.get("login_password") or ""

    if not username or not password:
        st.toast("请输入用户名和密码", icon="⚠️")
        return

    if not auth.login(username, password):
        st.toast("账号或密码错误，请检查后重试", icon="⚠️")
        return

    st.session_state["remembered_login"] = (
        {"username": username, "password": password}
        if st.session_state.get("login_remember")
        else None
    )
    flash("登录成功！", icon="✅")
    st.rerun()


def _handle_send_code() -> None:
    email = (st.session_state.get("reg_email") or "").strip()
    ok, message, demo_code = auth.send_verification_code(email)

    if demo_code:
        # 仅本地演示模式会走到这里：不发信，自动填入固定验证码，省去手动操作
        set_pending_inputs({"reg_code": demo_code})
        flash(f"{message}，演示验证码：{demo_code}", icon="📮")
        st.rerun()

    if ok:
        flash(message, icon="📮")
        st.rerun()

    st.toast(message, icon="⚠️")


def _handle_register() -> None:
    username = (st.session_state.get("reg_username") or "").strip()
    ok, message = auth.register(
        username,
        st.session_state.get("reg_email", ""),
        st.session_state.get("reg_password", ""),
        st.session_state.get("reg_confirm", ""),
        st.session_state.get("reg_code", ""),
    )

    if not ok:
        st.toast(message, icon="⚠️")
        return

    set_pending_inputs(
        {
            "auth_tab": "登录",
            "login_username": username,
            "reg_code": "",
            "reg_password": "",
            "reg_confirm": "",
        }
    )
    flash("注册成功，请前往登录", icon="🎉")
    st.rerun()


def render_auth_page() -> None:
    """渲染登录 / 注册页面。"""
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)

    st.title("🎓 课伴AI｜英语课本智能学习助手")
    st.markdown("**让每一次英语学习，都有清晰的下一步。**")
    st.caption("课本预习复习 · AI 作业批改 · 模拟试卷 · 学情诊断，一个应用全部搞定。")
    st.divider()

    _apply_remembered_login()
    tab_login, tab_register = st.tabs(
        ["登录", "注册"], default="登录", key="auth_tab"
    )

    with tab_login:
        st.text_input("用户名", key="login_username", placeholder="演示账号：student")
        st.text_input("密码", key="login_password", type="password", placeholder="演示密码：123456")
        st.checkbox("记住密码", key="login_remember", help="仅在本浏览器会话内记住账号密码")

        col_login, col_forgot = st.columns(2)
        with col_login:
            if st.button("登录", type="primary", use_container_width=True, key="login_submit"):
                _handle_login()
        with col_forgot:
            if st.button("忘记密码", use_container_width=True, key="login_forgot"):
                _forgot_password_dialog()

    with tab_register:
        st.text_input("用户名", key="reg_username", placeholder="2~20 个字符")
        st.text_input("邮箱", key="reg_email", placeholder="用于接收注册验证码")

        col_code, col_send = st.columns([2, 1], vertical_alignment="bottom")
        with col_code:
            st.text_input("邮箱验证码", key="reg_code", placeholder="6 位数字")
        with col_send:
            if st.button("获取验证码", use_container_width=True, key="reg_send_code"):
                _handle_send_code()

        st.text_input("密码", key="reg_password", type="password", placeholder="至少 6 位")
        st.text_input("确认密码", key="reg_confirm", type="password", placeholder="请再次输入密码")

        if st.button("提交注册", type="primary", use_container_width=True, key="reg_submit"):
            _handle_register()

    st.divider()
    st.caption("演示账号：student / 123456　　｜　　管理员账号：admin / 123456")


# --------------------------------------------------------------------------- #
# 侧边栏
# --------------------------------------------------------------------------- #
@st.dialog("客服留言", width="small")
def _message_dialog() -> None:
    user = auth.get_current_user()
    if not user:
        st.rerun(scope="app")

    st.caption("遇到问题或有功能建议？留言后管理员会在后台回复。")
    st.text_area(
        "留言内容",
        key="message_content",
        height=140,
        placeholder="例如：希望增加听力练习模块",
    )
    if st.button("提交留言", type="primary", use_container_width=True, key="message_submit"):
        content = (st.session_state.get("message_content") or "").strip()
        if len(content) < 2:
            st.toast("留言内容太短了，请至少输入 2 个字", icon="⚠️")
            return
        database.add_message({"username": user["username"], "content": content})
        set_pending_inputs({"message_content": ""})
        flash("留言提交成功！", icon="✅")
        st.rerun()


def render_sidebar_footer() -> None:
    """侧边栏底部的客服留言入口。"""
    with st.sidebar:
        st.divider()
        if st.button("💬 客服留言", use_container_width=True, key="sidebar_message"):
            _message_dialog()


# --------------------------------------------------------------------------- #
# 角色侧边导航
# --------------------------------------------------------------------------- #
def build_student_pages():
    return [
        st.Page(PAGE_HOME, title="首页", icon="🏠", default=True),
        st.Page(PAGE_PREVIEW, title="课本预习", icon="📖"),
        st.Page(PAGE_REVIEW, title="课本复习", icon="🔄"),
        st.Page(PAGE_HOMEWORK, title="作业中心", icon="✍️"),
        st.Page(PAGE_EXAM, title="模拟试卷", icon="📝"),
        st.Page(PAGE_MEMBER, title="会员中心", icon="👑"),
        st.Page(PAGE_DIAGNOSIS, title="学情诊断", icon="📊"),
    ]


def build_admin_pages():
    # 管理后台的三个菜单项共用同一个页面文件，靠 url_path 区分，页面内按标题选中对应 tab
    return [
        st.Page(PAGE_HOME, title="首页", icon="🏠", default=True),
        st.Page(PAGE_ADMIN, title="用户管理", icon="👥", url_path="admin-users"),
        st.Page(PAGE_ADMIN, title="消费记录", icon="🧾", url_path="admin-orders"),
        st.Page(PAGE_ADMIN, title="客服留言", icon="💬", url_path="admin-messages"),
    ]


def sync_navigation_state(page) -> None:
    """记录当前页面标题，并在切换到后台菜单时同步要展开的 tab。

    后台三个菜单项共用同一个页面文件，首页卡片通过 _pending_admin_tab
    指定要展开的板块，优先级高于菜单标题本身。
    """
    title = getattr(page, "title", "") or ""
    if st.session_state.get("_current_page") == title:
        return
    st.session_state["_current_page"] = title
    if title in ADMIN_SECTIONS:
        st.session_state["admin_active_tab"] = st.session_state.pop("_pending_admin_tab", title)


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> None:
    apply_pending_inputs()
    init_session_state()
    show_flash()

    user = auth.get_current_user()

    if user is None:
        render_auth_page()
        st.stop()

    user_menu.render_sidebar_user()

    page = st.navigation(build_admin_pages() if user.get("role") == "admin" else build_student_pages())
    sync_navigation_state(page)
    render_sidebar_footer()

    page.run()


main()
