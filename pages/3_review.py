"""课本复习：单元知识点总览（词汇 / 语法 / 语篇）与单元练习、7 天错题巩固计划。"""

from __future__ import annotations

import streamlit as st

from components.cards import status_tag
from core import auth, database, tutor_ai

user = auth.require_login()
st.title("🔄 课本复习")
st.caption("先看知识点掌握情况，再用 5 道题检验，最后生成 7 天错题巩固计划。")

unit = st.selectbox(
    "选择学习单元",
    tutor_ai.UNITS,
    key="current_unit",
    help="与首页、预习页面共用同一个单元选择",
)
content = tutor_ai.get_unit_content(unit)

tab_knowledge, tab_practice = st.tabs(["单元知识点总览", "单元练习题"], key="review_tabs")

# --------------------------------------------------------------------------- #
# Tab1 单元知识点总览
# --------------------------------------------------------------------------- #
with tab_knowledge:
    st.subheader("知识点掌握情况")
    modules = (("vocab", "词汇模块"), ("grammar", "语法模块"), ("discourse", "语篇模块"))
    for key, label in modules:
        module = content["knowledge"][key]
        mastery = module["mastery"]
        tag_type = "success" if mastery >= 85 else ("warn" if mastery >= 70 else "danger")
        with st.container(border=True):
            col_title, col_tag = st.columns([3, 1], vertical_alignment="center")
            with col_title:
                st.markdown(f"**{label}｜{module['summary']}**")
            with col_tag:
                status_tag(f"掌握度 {mastery}%", tag_type)
            for point in module["points"]:
                st.markdown(f"- {point}")

    st.divider()
    st.subheader("单词掌握统计")
    stats = content["vocab_stats"]
    col_mastered, col_review = st.columns(2)
    col_mastered.metric("已掌握词汇", f"{stats['mastered']} 个", border=True)
    col_review.metric("待巩固词汇", f"{stats['to_review']} 个", border=True)
    st.caption("待巩固词汇会在 7 天复习计划中自动安排背诵任务。")

# --------------------------------------------------------------------------- #
# Tab2 单元练习题
# --------------------------------------------------------------------------- #
with tab_practice:
    st.subheader("单元练习（共 5 题）")
    questions = content["review_quiz"]

    for index, question in enumerate(questions):
        st.markdown(f"**{index + 1}. {question['question']}**")
        st.radio(
            f"第 {index + 1} 题",
            question["options"],
            key=f"review_q_{unit}_{index}",
            label_visibility="collapsed",
        )

    if st.button("提交作答", type="primary", key=f"review_submit_{unit}"):
        answers = {str(index): st.session_state.get(f"review_q_{unit}_{index}") for index in range(len(questions))}
        if any(value is None for value in answers.values()):
            st.toast("还有题目没有作答，请全部完成后提交", icon="⚠️")
        else:
            result = tutor_ai.grade_quiz(unit, "review", answers)
            mastery, level = tutor_ai.get_mastery_score(
                seed=f"{unit}-review-{result['correct_count']}", base=result["score"]
            )
            result.update({"unit": unit, "mastery": mastery, "level": level})
            st.session_state["review_result"] = result
            database.add_learning_record(
                user["username"],
                {"module": "课本复习", "unit": unit, "score": result["score"], "level": level},
            )

    result = st.session_state.get("review_result")
    if result and result.get("unit") == unit:
        st.divider()
        st.subheader("作答结果")
        col_score, col_right, col_mastery = st.columns(3)
        col_score.metric("客观得分", f"{result['score']} 分")
        col_right.metric("答对题数", f"{result['correct_count']} / {result['total']}")
        col_mastery.metric("AI 掌握度", f"{result['mastery']} 分")

        status_tag(f"本次掌握度：{result['level']}", tutor_ai.level_tag_type(result["level"]))

        with st.expander("查看逐题解析", expanded=False):
            for item in result["details"]:
                mark = "✅" if item["is_right"] else "❌"
                st.markdown(f"{mark} **{item['index']}. {item['question']}**")
                st.caption(f"你的答案：{item['your_answer']}　｜　正确答案：{item['answer']}")
                st.caption(f"解析：{item['explain']}")

        if st.button("生成 7 天错题巩固计划", key=f"review_plan_{unit}"):
            st.session_state["review_plan"] = tutor_ai.gen_study_plan("review", unit)
            st.toast("已生成 7 天错题巩固计划", icon="🗓️")

    plan = st.session_state.get("review_plan")
    if plan and plan.get("type") == "review" and unit in plan.get("title", ""):
        st.divider()
        st.subheader(f"🗓️ {plan['title']}")
        st.caption(plan["summary"])
        for day in plan["days"]:
            with st.container(border=True):
                st.markdown(f"**第 {day['day']} 天 · {day['title']}**（建议 {day['minutes']} 分钟）")
                for task in day["tasks"]:
                    st.markdown(f"- {task}")
                st.caption(f"对应知识点：{'；'.join(day['unit_points'])}")
        for tip in plan["tips"]:
            st.caption(f"💡 {tip}")
