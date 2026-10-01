"""会员体系：VIP 判定、套餐配置、模拟支付、VIP 权限拦截。

所有页面的 VIP 校验统一走 check_vip_permission()，禁止在页面里硬编码角色判断。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from core import auth, database

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

MEMBER_PAGE = "pages/6_membership.py"

# 会员套餐：月卡 10 元 / 30 天，季卡 20 元 / 90 天，年卡 60 元 / 365 天（推荐）
PLANS: dict[str, dict] = {
    "月卡": {
        "name": "月卡",
        "price": 10,
        "days": 30,
        "recommended": False,
        "benefits": [
            "解锁全部 VIP 学习功能 30 天",
            "作业 AI 批改逐句解析",
            "模拟试卷全板块开放",
        ],
    },
    "季卡": {
        "name": "季卡",
        "price": 20,
        "days": 90,
        "recommended": False,
        "benefits": [
            "解锁全部 VIP 学习功能 90 天",
            "含月卡全部权益",
            "7 天错题巩固计划随时生成",
            "学情诊断四维能力跟踪",
        ],
    },
    "年卡": {
        "name": "年卡",
        "price": 60,
        "days": 365,
        "recommended": True,
        "benefits": [
            "解锁全部 VIP 学习功能 365 天",
            "含季卡全部权益",
            "全年教材单元内容同步更新",
            "新功能优先体验资格",
        ],
    },
}

PLAN_ORDER = ("月卡", "季卡", "年卡")

# 权益对比表：(权益说明, 免费版是否可用, VIP 是否可用)
FEATURE_MATRIX = (
    ("课本预习 · 课文导读与核心词汇", True, True),
    ("课本复习 · 单元知识点与练习", True, True),
    ("作业 AI 批改 · 总分与对错统计", True, True),
    ("作业 AI 批改 · 逐句错误解析与修改建议", False, True),
    ("模拟试卷 · 阅读 / 语言运用 / 书面写作", False, True),
    ("学情诊断 · 四维能力雷达图", False, True),
    ("个性化学习计划 · 预习 / 复习计划生成", False, True),
    ("错题归因 · 四维错题占比分析", False, True),
)


# --------------------------------------------------------------------------- #
# VIP 判定
# --------------------------------------------------------------------------- #
def _parse_expire(raw: str | None) -> datetime | None:
    """兼容 "2026-10-01 12:00:00" 与 "2026-10-01" 两种写法。"""
    if not raw:
        return None
    text = str(raw).strip()
    try:
        return datetime.strptime(text, DATE_FORMAT)
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def is_vip(user: dict | None) -> bool:
    """读取 vip_until 并与当前时间对比，判断会员是否仍在有效期内。"""
    if not user:
        return False
    expire = _parse_expire(user.get("vip_until"))
    return bool(expire and expire >= datetime.now())


def vip_until_text(user: dict | None) -> str:
    """会员到期时间文案，未开通返回提示语。"""
    expire = _parse_expire((user or {}).get("vip_until"))
    if not expire or expire < datetime.now():
        return "暂未开通"
    return expire.strftime("%Y年%m月%d日 %H:%M")


# --------------------------------------------------------------------------- #
# 模拟支付
# --------------------------------------------------------------------------- #
def process_payment(username: str, plan_name: str) -> dict:
    """模拟支付：计算到期时间、更新用户 VIP、写入订单记录。"""
    plan = PLANS.get(plan_name)
    if plan is None:
        return {"ok": False, "message": f"未知套餐：{plan_name}"}

    user = database.get_user_by_username(username)
    if user is None:
        return {"ok": False, "message": "用户不存在，请重新登录"}

    # 续费时从当前到期时间往后顺延，未到期不浪费剩余天数
    current_expire = _parse_expire(user.get("vip_until"))
    start = current_expire if current_expire and current_expire > datetime.now() else datetime.now()
    new_expire = start + timedelta(days=plan["days"])
    expire_text = new_expire.strftime(DATE_FORMAT)

    database.update_user(username, {"vip_until": expire_text, "vip_plan": plan["name"]})
    order = database.add_order(
        {
            "username": username,
            "plan_name": plan["name"],
            "amount": plan["price"],
            "days": plan["days"],
            "vip_until": expire_text,
            "status": "已支付",
            "pay_method": "模拟支付",
        }
    )
    auth.refresh_current_user()

    return {
        "ok": True,
        "message": f"{plan['name']}开通成功",
        "order_id": order["order_id"],
        "vip_until": expire_text,
        "amount": plan["price"],
    }


# --------------------------------------------------------------------------- #
# 权限拦截
# --------------------------------------------------------------------------- #
def _page_key() -> str:
    return str(st.session_state.get("_current_page", "unknown_page"))


def _gate_flag_key() -> str:
    return f"{auth.GATE_FLAG_PREFIX}{_page_key()}"


@st.dialog("VIP专属功能", width="small")
def _vip_dialog() -> None:
    st.write("该功能仅VIP会员可用，前往会员中心解锁全部学习能力。")
    st.caption("会员中心提供月卡 / 季卡 / 年卡三档套餐，支持模拟支付，开通后立即生效。")
    col_cancel, col_go = st.columns(2)
    if col_cancel.button("取消", key="vip_gate_cancel", use_container_width=True):
        st.rerun(scope="app")
    if col_go.button("前往会员中心", key="vip_gate_go", type="primary", use_container_width=True):
        st.session_state.pop(_gate_flag_key(), None)
        try:
            st.switch_page(MEMBER_PAGE)
        except Exception:
            st.toast("请在左侧菜单中打开「会员中心」", icon="👑")


def _render_locked_notice() -> None:
    """弹窗被取消后展示的占位内容，避免页面出现空白。"""
    with st.container(border=True):
        st.markdown("#### 👑 VIP 专属内容")
        st.write("该功能仅 VIP 会员可用，开通后可解锁全部学习能力。")
        if st.button("前往会员中心", type="primary", key=f"vip_locked_go_{_page_key()}"):
            try:
                st.switch_page(MEMBER_PAGE)
            except Exception:
                st.toast("请在左侧菜单中打开「会员中心」", icon="👑")


def check_vip_permission() -> bool:
    """VIP 权限拦截：是会员直接返回 True，否则弹出拦截弹窗并返回 False。

    页面用法：
        if not vip.check_vip_permission():
            st.stop()
    """
    user = auth.get_current_user()
    if user is None:
        return False

    flag_key = _gate_flag_key()
    if is_vip(user):
        st.session_state.pop(flag_key, None)
        return True

    if not st.session_state.get(flag_key):
        st.session_state[flag_key] = True
        _vip_dialog()
    else:
        _render_locked_notice()
    return False
