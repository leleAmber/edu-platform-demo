"""作业中心：左栏录入作业，右栏展示 AI 批改结果（免费版只给总分，VIP 给逐句解析）。"""

from __future__ import annotations

import streamlit as st

from components.cards import goto_page
from core import auth, database, tutor_ai, vip

PAGE_MEMBER = "pages/6_membership.py"
PAGE_DIAGNOSIS = "pages/7_diagnosis.py"

user = auth.require_login()
is_vip = vip.is_vip(user)

st.title("✍️ 作业中心")
st.caption("粘贴你的英语作文或课后习题，AI 会按句子逐条批改并给出修改建议。")

column_input, column_result = st.columns([1, 1], gap="large")

# --------------------------------------------------------------------------- #
# 左栏：作业录入
# --------------------------------------------------------------------------- #
with column_input:
    st.subheader("作业录入")
    homework_text = st.text_area(
        "作业内容",
        key="homework_text",
        height=320,
        placeholder="粘贴你的英语作文/课后习题",
    )
    st.caption("支持整段粘贴，AI 会先断句，再逐句检查语法、搭配与标点。")

    if st.button("提交 AI 批改", type="primary", key="homework_submit", width="stretch"):
        if len(homework_text.strip()) < 10:
            st.toast("内容太短了，请至少输入一个完整的英语句子", icon="⚠️")
        else:
            with st.spinner("AI 正在逐句批改…"):
                result = tutor_ai.homework_correct(homework_text)
            st.session_state["homework_result"] = result
            database.add_learning_record(
                user["username"],
                {
                    "module": "作业批改",
                    "unit": st.session_state.get("current_unit", ""),
                    "score": result["total_score"],
                    "level": tutor_ai.mastery_level(result["total_score"]),
                },
            )
            st.toast("批改完成！", icon="✅")

# --------------------------------------------------------------------------- #
# 右栏：批改结果
# --------------------------------------------------------------------------- #
with column_result:
    st.subheader("批改结果")
    result = st.session_state.get("homework_result")

    # 提交后开通了会员：自动按 VIP 口径重新批改一次，展示完整解析
    if is_vip and result and "details" not in result and st.session_state.get("homework_text"):
        result = tutor_ai.homework_correct(st.session_state["homework_text"])
        st.session_state["homework_result"] = result

    if not result:
        st.info("提交作业后，这里会显示 AI 批改结果。")
    else:
        col_total, col_right, col_wrong = st.columns(3)
        col_total.metric("总分", f"{result['total_score']} 分")
        col_right.metric("正确句子", result["right_count"], border=True)
        col_wrong.metric("待修改句子", result["wrong_count"], border=True)

        if not is_vip:
            st.info("开通 VIP 查看逐句错误解析、修改建议。")
            if st.button("前往会员中心开通", key="homework_upgrade", width="stretch"):
                goto_page(PAGE_MEMBER)
        else:
            st.markdown(f"**AI 评语**：{result.get('comment', '')}")

            details = result.get("details", [])
            if not details:
                st.success("未检测到明显语法错误，继续保持！")
            else:
                st.caption(f"共发现 {len(details)} 处需要修改的句子，点击展开查看解析。")
                for item in details:
                    with st.expander(f"第 {item['index']} 句｜{item['error_type']}"):
                        st.markdown(f"**原句**：{item['original']}")
                        st.markdown(f"**修改后**：{item['corrected']}")
                        st.markdown(f"**错误解析**：{item['explain']}")

            error_types = result.get("error_types") or {}
            if error_types:
                st.markdown("**错误类型分布**")
                for error_type, count in sorted(error_types.items(), key=lambda pair: -pair[1]):
                    st.markdown(f"- {error_type}：{count} 处")

            if st.button("查看四维能力评估", key="homework_to_diagnosis", width="stretch"):
                goto_page(PAGE_DIAGNOSIS)
