"""课本预习：课文导读（长难句解析 + 核心词汇）与预习练习、3 天预习计划。"""

from __future__ import annotations

import streamlit as st

from components.cards import knowledge_card, status_tag
from core import auth, database, tutor_ai

user = auth.require_login()
st.title("📖 课本预习")
st.caption("先整体感知课文，再拆解长难句，最后用 5 道小题检验预习效果。")

unit = st.selectbox(
    "选择学习单元",
    tutor_ai.UNITS,
    key="current_unit",
    help="与首页、复习页面共用同一个单元选择",
)
content = tutor_ai.get_unit_content(unit)
st.caption(f"单元主题：{content['theme']}")

tab_read, tab_practice = st.tabs(["课文导读", "预习练习"], key="preview_tabs")

# --------------------------------------------------------------------------- #
# Tab1 课文导读
# --------------------------------------------------------------------------- #
with tab_read:
    st.subheader("课文节选")
    for paragraph in content["passages"]:
        st.markdown(f"**{paragraph['heading']}**")
        st.write(paragraph["text"])

    st.divider()
    st.subheader("AI 长难句解析")
    st.caption("自动识别课文中的长难句，拆分主干与修饰成分并给出中文翻译。")
    for index, item in enumerate(content["long_sentences"], 1):
        with st.expander(f"长难句 {index}｜{item['sentence'][:28]}…", expanded=index == 1):
            st.markdown(f"**原句**：{item['sentence']}")
            st.markdown(f"**句子主干**：{item['skeleton']}")
            st.markdown(f"**修饰成分**：{item['modifiers']}")
            st.markdown(f"**参考翻译**：{item['translation']}")

    st.divider()
    st.subheader("核心词汇")
    st.caption("本单元 6 个高频词汇，建议每个词各造一个句子。")
    word_columns = st.columns(3)
    for index, word in enumerate(content["words"]):
        with word_columns[index % 3]:
            knowledge_card(word["word"], word["pos"], word["explain"], word["sentence"])

# --------------------------------------------------------------------------- #
# Tab2 预习练习
# --------------------------------------------------------------------------- #
with tab_practice:
    st.subheader("预习自测（共 5 题）")
    questions = content["preview_quiz"]

    for index, question in enumerate(questions):
        st.markdown(f"**{index + 1}. {question['question']}**")
        st.radio(
            f"第 {index + 1} 题",
            question["options"],
            key=f"preview_q_{unit}_{index}",
            label_visibility="collapsed",
        )

    if st.button("提交答案", type="primary", key=f"preview_submit_{unit}"):
        answers = {str(index): st.session_state.get(f"preview_q_{unit}_{index}") for index in range(len(questions))}
        if any(value is None for value in answers.values()):
            st.toast("还有题目没有作答，请全部完成后提交", icon="⚠️")
        else:
            result = tutor_ai.grade_quiz(unit, "preview", answers)
            mastery, level = tutor_ai.get_mastery_score(
                seed=f"{unit}-preview-{result['correct_count']}", base=result["score"]
            )
            result.update({"unit": unit, "mastery": mastery, "level": level})
            st.session_state["preview_result"] = result
            database.add_learning_record(
                user["username"],
                {"module": "课本预习", "unit": unit, "score": result["score"], "level": level},
            )

    result = st.session_state.get("preview_result")
    if result and result.get("unit") == unit:
        st.divider()
        st.subheader("批改结果")
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

        if st.button("生成预习学习计划", key=f"preview_plan_{unit}"):
            st.session_state["preview_plan"] = tutor_ai.gen_study_plan("preview", unit)
            st.toast("已根据本次作答生成 3 天预习计划", icon="🗓️")

    plan = st.session_state.get("preview_plan")
    if plan and plan.get("type") == "preview" and unit in plan.get("title", ""):
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
