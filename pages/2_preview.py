"""课本预习：单元单词 + 核心句型 + 基础练习（内容只来自当前选中教材）。"""

from __future__ import annotations

import streamlit as st

from components import book_selector
from components.cards import knowledge_card, status_tag
from core import auth, database, tutor_ai

user = auth.require_login()
st.title("📖 课本预习")
st.caption("先掌握本单元单词与核心句型，再用基础练习检验预习效果。")

book, unit = book_selector.render_selectors()
content = tutor_ai.get_unit_content(book, unit)
st.caption(f"单元主题：{content['theme']}")

tab_words, tab_patterns, tab_practice = st.tabs(["单元单词", "核心句型", "基础练习"], key="preview_tabs")

# --------------------------------------------------------------------------- #
# Tab1 单元单词
# --------------------------------------------------------------------------- #
with tab_words:
    st.subheader("单元单词")
    words = content["words"]
    if not words:
        st.info("本单元暂无单词数据，请先运行 scripts/extract_textbooks.py 生成教材内容。")
    else:
        st.caption(f"本单元 {len(words)} 个核心词汇，建议每个词各造一个句子。")
        word_columns = st.columns(3)
        for index, word in enumerate(words):
            with word_columns[index % 3]:
                knowledge_card(
                    word.get("word", ""),
                    word.get("pos", ""),
                    word.get("explain", ""),
                    word.get("sentence", ""),
                )

# --------------------------------------------------------------------------- #
# Tab2 核心句型
# --------------------------------------------------------------------------- #
with tab_patterns:
    st.subheader("核心句型")
    patterns = content.get("sentence_patterns", [])
    if not patterns:
        st.info("本单元暂无句型数据。")
    else:
        for index, item in enumerate(patterns, 1):
            with st.expander(f"句型 {index}｜{item.get('pattern', '')[:30]}", expanded=index == 1):
                st.markdown(f"**句型**：{item.get('pattern', '')}")
                if item.get("explain"):
                    st.markdown(f"**讲解**：{item['explain']}")
                if item.get("example"):
                    st.markdown(f"**例句**：{item['example']}")
                if item.get("translation"):
                    st.caption(f"参考翻译：{item['translation']}")

# --------------------------------------------------------------------------- #
# Tab3 基础练习
# --------------------------------------------------------------------------- #
with tab_practice:
    st.subheader("基础练习（共 5 题）")
    questions = content["preview_quiz"]

    if not questions:
        st.info("本单元暂无练习题（题库不足）。生成后会自动从题库抽取。")
    else:
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
                result = tutor_ai.grade_quiz(book, unit, "preview", answers)
                mastery, level = tutor_ai.get_mastery_score(
                    seed=f"{book}-{unit}-preview-{result['correct_count']}", base=result["score"]
                )
                result.update({"unit": unit, "mastery": mastery, "level": level})
                st.session_state["preview_result"] = result
                database.add_learning_record(
                    user["username"],
                    {"module": "课本预习", "unit": f"{book}·{unit}", "score": result["score"], "level": level},
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
            st.session_state["preview_plan"] = tutor_ai.gen_study_plan("preview", unit, book)
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
