import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
import time
from datetime import datetime
from email.message import EmailMessage

import streamlit as st

import database as store


st.set_page_config(page_title="课伴AI | 英语课本智能学习助手", page_icon="📘", layout="wide")
store.init_db()

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap');
    :root { --ink:#172235; --muted:#718096; --blue:#2168f5; --line:#e8ecf2; }
    html, body, [class*="css"] { font-family:'DM Sans','Noto Sans SC',sans-serif; color:var(--ink); }
    .stApp { background:#f6f8fb; }
    [data-testid="stSidebar"] { background:#fff; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1 { font-size:20px; }
    .brand { display:flex; align-items:center; gap:10px; font-size:19px; font-weight:800; margin:8px 0 28px; }
    .brand-mark { display:grid; place-items:center; width:36px; height:36px; border-radius:10px; color:#fff; background:var(--blue); }
    .hero { display:grid; grid-template-columns:1.2fr .8fr; gap:24px; padding:32px 36px; color:#fff; border-radius:14px; background:linear-gradient(115deg,#16439f,#2175d9 65%,#299caa); }
    .hero h1 { margin:10px 0; color:white; font-size:32px; line-height:1.3; }
    .hero p { max-width:650px; color:#e2edff; line-height:1.8; }
    .hero-book { align-self:center; justify-self:center; width:180px; padding:25px 20px 21px; border-radius:7px 16px 16px 7px; transform:rotate(-7deg); color:#2867cb; background:#fff; box-shadow:-8px 8px #17488c,0 18px 24px #0e2b6166; font-weight:800; }
    .hero-book span { display:block; margin-top:16px; color:#7d9acd; font-size:11px; }
    .eyebrow { color:#2168f5; font-size:11px; font-weight:800; letter-spacing:1px; }
    .panel { padding:20px; border:1px solid var(--line); border-radius:10px; background:#fff; }
    .panel h3 { margin-top:0; }
    .muted { color:var(--muted); }
    .tag { display:inline-block; padding:4px 9px; border-radius:6px; color:#137966; background:#e8faf5; font-size:12px; font-weight:700; }
    .lesson { padding:14px 16px; border-left:3px solid #b9cdf5; color:#526176; background:#f8faff; line-height:1.9; }
    .word { padding:15px; border:1px solid var(--line); border-radius:9px; background:#fff; }
    .word strong { color:#1f5ecc; font-size:18px; }
    .callout { padding:15px; border:1px solid #d8e9e6; border-radius:9px; background:#f1fbf9; line-height:1.8; }
    .stButton>button { border-radius:7px; font-weight:700; }
    div[data-testid="stMetric"] { padding:15px; border:1px solid var(--line); border-radius:9px; background:#fff; }
    @media(max-width:700px) { .hero { grid-template-columns:1fr; padding:24px; } .hero h1 { font-size:25px; } .hero-book { display:none; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def setting(name, default=""):
    value = os.environ.get(name)
    if value is not None:
        return value
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def dev_mode():
    return str(setting("AUTH_DEV_MODE", "0")).strip().lower() in ("1", "true", "yes", "on")


def otp_digest(email, code):
    secret = str(setting("AUTH_OTP_SECRET", "")).strip()
    if not secret:
        raise RuntimeError("未配置 AUTH_OTP_SECRET")
    payload = (email.strip().lower() + ":" + code).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def send_otp_email(email, code):
    host = str(setting("SMTP_HOST", "")).strip()
    port = int(setting("SMTP_PORT", "465"))
    login = str(setting("SMTP_LOGIN", "")).strip()
    password = str(setting("SMTP_PASSWORD", ""))
    sender = str(setting("SMTP_SENDER_EMAIL", login)).strip()
    use_ssl = str(setting("SMTP_USE_SSL", "true")).strip().lower() in ("1", "true", "yes", "on")
    if not all((host, login, password, sender)):
        raise RuntimeError("SMTP 配置不完整，请检查 Streamlit secrets")
    message = EmailMessage()
    message["Subject"] = "课伴AI邮箱验证码"
    message["From"] = sender
    message["To"] = email
    message.set_content("您好，您的课伴AI注册验证码为：{}。验证码10分钟内有效，请勿转发。".format(code))
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as smtp:
            smtp.login(login, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(login, password)
            smtp.send_message(message)


def is_vip(user):
    return bool(user and user.get("vip_until") and user["vip_until"] > time.time())


def date_text(value):
    if not value:
        return "-"
    return datetime.fromtimestamp(value).strftime("%Y-%m-%d")


def login_view():
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        st.markdown(
            '<div class="hero" style="min-height:590px;display:block;padding:54px">'
            '<div style="font-size:18px;font-weight:800">◈ &nbsp;课伴AI</div>'
            '<div style="padding-top:70px"><div style="color:#cce1ff;font-size:12px;font-weight:700">ENGLISH LEARNING COMPANION</div>'
            '<h1>让每一次英语学习<br>都有清晰的下一步。</h1>'
            '<p>按课本单元理解词汇、句法与语篇逻辑，积累可见的进步。</p></div>'
            '<div style="padding-top:55px;color:#e2eeff;line-height:2.2">✓ &nbsp;课本预习与单元复习<br>✓ &nbsp;作业反馈与个性化计划<br>✓ &nbsp;持续记录学习进展</div></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        login_tab, register_tab = st.tabs(["登录", "注册"])
        with login_tab:
            st.markdown("### 登录课伴AI")
            st.caption("欢迎回来，继续你的英语学习")
            with st.form("login_form"):
                username = st.text_input("用户名", placeholder="请输入用户名")
                password = st.text_input("密码", type="password", placeholder="请输入密码")
                submit = st.form_submit_button("登录", type="primary", use_container_width=True)
            if submit:
                user = store.authenticate(username, password)
                if user:
                    st.session_state.user_id = user["id"]
                    st.rerun()
                st.error("用户名或密码不正确")
            with st.expander("演示账号"):
                st.write("学生：`student / 123456`　管理员：`admin / 123456`")
        with register_tab:
            st.markdown("### 创建学习账号")
            st.caption("邮箱验证码有效期为 10 分钟")
            with st.form("send_code_form"):
                code_email = st.text_input("邮箱地址", key="otp_email", placeholder="name@example.com")
                send_code = st.form_submit_button("发送邮箱验证码", use_container_width=True)
            if send_code:
                email = code_email.strip().lower()
                if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                    st.error("请输入有效邮箱地址")
                elif not setting("AUTH_OTP_SECRET", ""):
                    st.error("验证码服务尚未配置，请检查 AUTH_OTP_SECRET")
                else:
                    code = "{:06d}".format(secrets.randbelow(1000000))
                    try:
                        if not store.issue_otp(email, otp_digest(email, code)):
                            st.warning("请稍后再试，每个邮箱 60 秒内只能发送一次")
                        else:
                            if not dev_mode():
                                send_otp_email(email, code)
                            st.session_state.otp_email_sent = email
                            st.success("验证码已发送，请检查邮箱" if not dev_mode() else "开发模式验证码已生成")
                            if dev_mode():
                                st.info("开发验证码：{}".format(code))
                    except Exception as exc:
                        st.error("发送失败：{}".format(str(exc)))
            with st.form("register_form"):
                reg_name = st.text_input("用户名", placeholder="2-20 个字符")
                reg_email = st.text_input("注册邮箱", placeholder="需与接收验证码的邮箱一致")
                reg_password = st.text_input("密码", type="password", placeholder="至少 6 位")
                reg_confirm = st.text_input("确认密码", type="password")
                reg_code = st.text_input("邮箱验证码", max_chars=6, placeholder="6 位数字")
                register = st.form_submit_button("注册并开始学习", type="primary", use_container_width=True)
            if register:
                email = reg_email.strip().lower()
                if len(reg_name.strip()) < 2 or len(reg_name.strip()) > 20:
                    st.error("用户名需为 2-20 个字符")
                elif not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                    st.error("请输入有效邮箱地址")
                elif len(reg_password) < 6:
                    st.error("密码至少 6 位")
                elif reg_confirm != reg_password:
                    st.error("两次输入的密码不一致")
                elif not re.fullmatch(r"\d{6}", reg_code):
                    st.error("请输入 6 位数字验证码")
                else:
                    try:
                        if not store.verify_otp(email, otp_digest(email, reg_code)):
                            st.error("验证码错误、过期或已超过尝试次数")
                        else:
                            user = store.create_user(reg_name.strip(), email, reg_password)
                            st.session_state.user_id = user["id"]
                            st.success("注册成功，正在进入课伴AI")
                            st.rerun()
                    except Exception as exc:
                        if "UNIQUE constraint failed" in str(exc):
                            st.error("用户名或邮箱已注册")
                        else:
                            st.error("注册失败，请稍后重试")


def title(eyebrow, heading, subtitle=""):
    st.markdown('<div class="eyebrow">{}</div>'.format(eyebrow), unsafe_allow_html=True)
    st.title(heading)
    if subtitle:
        st.caption(subtitle)


def record_and_rerun(user, kind, score, message):
    store.record_learning(user["id"], kind, score)
    st.session_state.notice = message
    st.rerun()


def home_page(user):
    member = "VIP 会员" if is_vip(user) else "免费版"
    st.markdown(
        '<div class="hero"><div><div class="eyebrow" style="color:#cce1ff">英语 · 学习助手</div>'
        '<h1>今天，也给英语学习<br>一个清晰的开始。</h1>'
        '<p>按课本单元掌握核心词汇、句法与语篇逻辑，完成一次小而确定的进步。</p>'
        '<span class="tag">当前状态　{}</span></div><div class="hero-book">ENGLISH<br><span style="font-size:19px;color:#2867cb">必修一</span><span>Unit 01</span></div></div>'.format(member),
        unsafe_allow_html=True,
    )
    st.markdown("#### 选择学习单元")
    st.selectbox("当前单元", ["Unit 1 Teenage Life", "Unit 2 Travelling Around", "Unit 3 Sports and Fitness", "Unit 4 Natural Disasters"], label_visibility="collapsed")
    cols = st.columns(4)
    entries = [("课本预习", "理解课文、生词和长难句", "课本预习"), ("课本复习", "回顾单元知识点并巩固记忆", "课本复习"), ("作业中心", "获得英语作业反馈与错题归因", "作业中心"), ("模拟试卷", "检验综合掌握度 · VIP", "模拟试卷")]
    for col, (name, desc, route) in zip(cols, entries):
        with col:
            st.markdown('<div class="panel"><div class="eyebrow">LEARNING</div><h3>{}</h3><p class="muted">{}</p></div>'.format(name, desc), unsafe_allow_html=True)
            if st.button("进入 →", key="home_" + route, use_container_width=True):
                st.session_state.pending_route = route
                st.rerun()
    st.markdown("#### 今日学习建议")
    a, b, c = st.columns(3)
    with a:
        st.markdown('<div class="panel"><div class="eyebrow">01 · 词汇</div><h4>复习 12 个高频词</h4><p class="muted">再巩固一次，记忆会更牢。</p></div>', unsafe_allow_html=True)
    with b:
        st.markdown('<div class="panel"><div class="eyebrow">02 · 句法</div><h4>看懂一条长难句</h4><p class="muted">从连接词和主干开始拆解。</p></div>', unsafe_allow_html=True)
    with c:
        st.markdown('<div class="panel"><div class="eyebrow">03 · 记录</div><h4>保持连续学习</h4><p class="muted">今天完成 15 分钟即可延续节奏。</p></div>', unsafe_allow_html=True)


def preview_page(user):
    title("TEXTBOOK PREVIEW", "课本预习", "从课文语境开始，先理解，再记忆。")
    st.selectbox("选择单元", ["Unit 1 Teenage Life", "Unit 2 Travelling Around", "Unit 3 Sports and Fitness", "Unit 4 Natural Disasters"])
    st.markdown("#### 课文导读 · Adam's Teenage Life")
    st.markdown('<div class="panel"><h3>Getting to know the new school</h3><div class="lesson">A week after the first day of senior high school, Adam is still trying to find his way around the new campus. He joined the football team and discovered that making friends can make a new life feel much easier.</div><div class="callout" style="margin-top:14px"><strong>✦ AI 长难句解读</strong><br>句子主干是 <b>Adam is trying...</b>，时间状语补充背景，to find his way around... 是不定式短语。先抓主干，再补充修饰信息。</div></div>', unsafe_allow_html=True)
    st.markdown("#### 本单元核心词汇")
    words = [("challenge", "n. 挑战；艰巨任务"), ("confused", "adj. 糊涂的；迷惑的"), ("recommend", "vt. 建议；推荐"), ("responsible", "adj. 负责的"), ("schedule", "n. 日程安排"), ("improve", "v. 改进；改善")]
    for row_index, row in enumerate((st.columns(3), st.columns(3))):
        for col, (word, meaning) in zip(row, words[row_index * 3 : row_index * 3 + 3]):
            with col:
                st.markdown('<div class="word"><strong>{}</strong><p class="muted">{}</p></div>'.format(word, meaning), unsafe_allow_html=True)
    st.markdown("#### 预习检测")
    left, right = st.columns(2)
    with left:
        if st.button("开始单词听写", type="primary"):
            record_and_rerun(user, "预习", 72, "听写已完成，预习评级已更新。")
    with right:
        if st.button("开始听力小练习"):
            record_and_rerun(user, "听力练习", 80, "听力练习已完成。")
    st.markdown('<div class="callout"><b>本次预习评级 · 72 分</b><br>评级依据：词汇识别、语篇理解与预习检测。<br>计划：今天复习 6 个易混词，明天拆解 2 个长难句，第 3 天完成听力练习。</div>', unsafe_allow_html=True)


def review_page(user):
    title("TEXTBOOK REVIEW", "课本复习", "把知识点串起来，再用练习确认掌握。")
    st.selectbox("复习单元", ["Unit 1 Teenage Life", "Unit 2 Travelling Around", "Unit 3 Sports and Fitness"])
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="panel"><div class="eyebrow">KNOWLEDGE MAP</div><h3>Unit 1 知识点回顾</h3><p>语法　名词短语与定语从句</p><p>词汇　teenager · volunteer · debate</p><p>语篇　校园生活类记叙文结构</p></div>', unsafe_allow_html=True)
    with b:
        st.markdown('<div class="panel"><div class="eyebrow">QUICK CHECK</div><h3>基础检测练习</h3><p>Adam joined the football ___.</p><p>The word “challenge” means...</p><p>Find the subject of the sentence.</p></div>', unsafe_allow_html=True)
        if st.button("提交检测", type="primary"):
            record_and_rerun(user, "单元复习", 80, "检测已完成，得分 80 分。")
    st.markdown('<div class="callout"><b>复习评级 · 稳步提升</b><br>本单元得分 80。下一步：订正从句边界错题 3 题，每天复习 6 个词并连续 3 天达到 90%。</div>', unsafe_allow_html=True)


def homework_page(user):
    title("AI HOMEWORK", "作业中心", "粘贴英语作业，快速得到错题反馈。")
    left, right = st.columns([1, 1])
    with left:
        text = st.text_area("作业文本", height=220, placeholder="例如：I am confusing about the schedule...")
        if st.button("提交 AI 批改", type="primary"):
            if not text.strip():
                st.warning("请先粘贴一段英语作业")
            else:
                st.session_state.homework_text = text
                store.record_learning(user["id"], "作业", 75)
    with right:
        st.markdown("#### 批改结果")
        if st.session_state.get("homework_text"):
            st.markdown('<div class="panel"><div class="eyebrow">AI GRADING · 演示反馈</div><h3>发现一处常见易错表达</h3><p><code>I am confusing about the schedule.</code></p><p>描述人的感受应使用 <b>confused</b>，建议改为：</p><div class="callout">I am confused about the schedule.</div><p class="muted">此处为规则示例反馈，生产环境需接入 AI 服务。</p></div>', unsafe_allow_html=True)
        else:
            st.info("提交一段作业后，这里会出现批改结果。")
    if is_vip(user):
        st.success("VIP：已解锁逐题讲解与四维能力评级")
    else:
        st.caption("免费版可查看简略反馈；开通 VIP 解锁逐题讲解。")


def exams_page(user):
    title("MOCK EXAM", "英语模拟试卷", "在完整题型中检验你的阶段性掌握。")
    st.markdown('<div class="panel"><h3>英语阶段模拟卷（一）</h3><p>听力 · 阅读 · 语言运用 · 写作　共 120 分　｜　预计 45 分钟</p></div>', unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.metric("阅读理解", "4 篇短文", "15 题")
    b.metric("语言运用", "完形填空", "语法填空")
    c.metric("写作输出", "应用文写作", "15 分")
    if st.button("开始模拟考试", type="primary"):
        record_and_rerun(user, "模拟考试", 0, "模拟考试已开始，计时功能为演示状态。")


def membership_page(user):
    title("MEMBERSHIP", "会员中心", "解锁完整 AI 讲解与英语学习资源。")
    if is_vip(user):
        st.success("当前会员有效期至 {}".format(date_text(user["vip_until"])))
    plans = [("月卡", 10, 30), ("年卡", 60, 365), ("季卡", 20, 90)]
    cols = st.columns(3)
    for col, (plan, price, days) in zip(cols, plans):
        with col:
            st.markdown('<div class="panel"><h3>{}</h3><p class="muted">{} 元 · {} 天</p><p>AI 作业逐题讲解</p><p>学习能力评级与模拟试卷</p></div>'.format(plan, price, days), unsafe_allow_html=True)
            if st.button("模拟开通", key="plan_" + plan, type="primary" if plan == "年卡" else "secondary", use_container_width=True):
                store.buy_membership(user["id"], plan, price, days)
                st.session_state.notice = "会员开通成功（演示支付）"
                st.rerun()
    st.warning("支付流程为本地演示，不会产生真实扣款。真实交易需要支付商户资质、后端订单与支付回调。")


def my_page(user):
    title("MY SPACE", "我的", "管理个人信息与学习设置。")
    c1, c2, c3 = st.columns(3)
    c1.metric("用户名", user["username"])
    c2.metric("会员状态", "VIP 会员" if is_vip(user) else "免费版")
    c3.metric("邮箱", user["email"])
    st.markdown("#### 最近学习记录")
    events = store.get_learning(user["id"])
    if events:
        st.dataframe([{"学习内容": row["kind"], "得分": row["score"], "时间": datetime.fromtimestamp(row["created_at"]).strftime("%Y-%m-%d %H:%M")} for row in events], width="stretch", hide_index=True)
    else:
        st.info("完成预习、复习或作业后，学习记录会显示在这里。")
    with st.form("message_form"):
        message = st.text_area("联系客服", placeholder="告诉我们你在学习中的问题或建议。")
        submit_message = st.form_submit_button("提交留言")
    if submit_message:
        if message.strip():
            store.add_message(user["id"], message)
            st.success("留言已提交")
        else:
            st.warning("请填写留言内容")


def admin_page():
    title("ADMINISTRATION", "管理后台", "用户、订单与客服留言")
    users, orders, messages, stats = store.get_admin_data()
    a, b, c = st.columns(3)
    a.metric("用户总数", stats["users"])
    b.metric("订单数", stats["orders"])
    c.metric("模拟营收", "¥{}".format(stats["revenue"]))
    users_tab, orders_tab, messages_tab = st.tabs(["用户管理", "消费记录", "客服留言"])
    with users_tab:
        st.dataframe([{"用户名": r["username"], "邮箱": r["email"], "角色": r["role"], "会员有效期": date_text(r["vip_until"]), "注册日期": date_text(r["created_at"])} for r in users], width="stretch", hide_index=True)
    with orders_tab:
        st.dataframe([{"用户名": r["username"], "套餐": r["plan"], "金额": "¥{}".format(r["price"]), "时间": date_text(r["created_at"])} for r in orders], width="stretch", hide_index=True)
    with messages_tab:
        if not messages:
            st.info("暂无客服留言")
        for row in messages:
            with st.expander("{} · {}".format(row["username"], date_text(row["created_at"]))):
                st.write(row["content"])
                if row["reply"]:
                    st.success("已回复：{}".format(row["reply"]))
                else:
                    with st.form("reply_{}".format(row["id"])):
                        reply = st.text_input("回复内容")
                        send = st.form_submit_button("保存回复")
                    if send and reply.strip():
                        store.reply_message(row["id"], reply)
                        st.rerun()


def main():
    if "user_id" not in st.session_state or not store.get_user(st.session_state.user_id):
        login_view()
        return
    user = store.get_user(st.session_state.user_id)
    pages = ["首页", "课本预习", "课本复习", "作业中心", "模拟试卷", "会员中心", "我的"]
    if user["role"] == "admin":
        pages.append("管理后台")
    pending_route = st.session_state.pop("pending_route", None)
    if pending_route in pages:
        st.session_state.navigation = pending_route
    with st.sidebar:
        st.markdown('<div class="brand"><span class="brand-mark">伴</span>课伴AI</div>', unsafe_allow_html=True)
        selected = st.radio("导航", pages, key="navigation", label_visibility="collapsed")
        st.divider()
        st.markdown("**{}**".format(user["username"]))
        st.caption("VIP 会员" if is_vip(user) else "免费版")
        if st.button("退出登录", use_container_width=True):
            del st.session_state.user_id
            st.session_state.pop("navigation", None)
            st.rerun()
    if st.session_state.get("notice"):
        st.toast(st.session_state.pop("notice"))
    routes = {
        "首页": home_page,
        "课本预习": preview_page,
        "课本复习": review_page,
        "作业中心": homework_page,
        "模拟试卷": exams_page,
        "会员中心": membership_page,
        "我的": my_page,
    }
    if selected == "管理后台" and user["role"] == "admin":
        admin_page()
    elif selected == "模拟试卷" and not is_vip(user):
        st.warning("模拟试卷为 VIP 专属，请先前往会员中心开通。")
        if st.button("查看会员方案"):
            st.session_state.pending_route = "会员中心"
            st.rerun()
    else:
        routes[selected](user)


main()
