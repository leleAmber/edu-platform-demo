"""模拟试卷：VIP 专属，含阅读理解、语言运用、书面写作三个板块。"""

from __future__ import annotations

import streamlit as st

from core import auth, database, tutor_ai, vip

user = auth.require_login()

# VIP 权限拦截：非会员直接弹出拦截弹窗，无法查看试卷内容
if not vip.check_vip_permission():
    st.stop()

st.title("📝 模拟试卷")

exam = tutor_ai.get_mock_exam()
st.caption(f"{exam['title']}｜满分 100 分｜建议用时 {exam['duration']} 分钟")


@st.dialog("开始模拟考试", width="small")
def confirm_exam_dialog() -> None:
    st.write("模拟考试开始，计时功能为演示版本。")
    st.caption("交卷后系统会自动评分，并给出各板块得分与学习建议。")
    col_cancel, col_start = st.columns(2)
    if col_cancel.button("取消", key="exam_cancel", width="stretch"):
        st.rerun(scope="app")
    if col_start.button("确认开始", type="primary", key="exam_confirm", width="stretch"):
        st.session_state["exam_started"] = True
        st.session_state.pop("exam_result", None)
        st.rerun(scope="app")


def render_exam_paper() -> None:
    """渲染试卷内容与答题区域。"""
    for section in exam["sections"]:
        with st.container(border=True):
            st.markdown(f"#### {section['name']}（{section['score']} 分）")

            if section["key"] == "writing":
                st.markdown(f"**题目**：{section['prompt']}")
                for requirement in section["requirements"]:
                    st.markdown(f"- {requirement}")
                st.text_area(
                    "作文作答区",
                    key="exam_writing",
                    height=220,
                    placeholder="在此写下你的英语短文…",
                    label_visibility="collapsed",
                )
                continue

            if section.get("passage"):
                st.write(section["passage"])
                st.divider()

            for index, question in enumerate(section["questions"], 1):
                st.markdown(f"**{index}. {question['question']}**")
                st.radio(
                    f"{section['key']}-{question['id']}",
                    question["options"],
                    key=f"exam_{question['id']}",
                    label_visibility="collapsed",
                )


def render_exam_result(result: dict) -> None:
    st.divider()
    st.subheader("考试结果")
    col_total, col_objective, col_writing = st.columns(3)
    col_total.metric("总分", f"{result['total']} / {result['full_score']}")
    col_objective.metric("客观题得分", f"{result['objective_score']} 分")
    col_writing.metric("写作得分", f"{result['writing_score']} 分")

    st.markdown(f"**AI 评语**：{result['comment']}")

    with st.expander("查看客观题解析", expanded=False):
        for item in result["details"]:
            mark = "✅" if item["is_right"] else "❌"
            st.markdown(f"{mark} **{item['question']}**")
            st.caption(f"你的答案：{item['your_answer']}　｜　正确答案：{item['answer']}")
            st.caption(f"解析：{item['explain']}")

    with st.expander("查看写作点评", expanded=True):
        for note in result["writing_notes"]:
            st.markdown(f"- {note}")

    if st.button("再考一次", key="exam_restart"):
        st.session_state["exam_started"] = False
        st.session_state.pop("exam_result", None)
        for section in exam["sections"]:
            for question in section["questions"]:
                st.session_state.pop(f"exam_{question['id']}", None)
        st.session_state.pop("exam_writing", None)
        st.rerun()


result = st.session_state.get("exam_result")
if result:
    render_exam_result(result)
elif not st.session_state.get("exam_started"):
    with st.container(border=True):
        st.markdown("#### 开始前须知")
        st.markdown(
            "- 试卷包含阅读理解、语言运用、书面写作三个板块，满分 100 分\n"
            "- 演示版本的计时功能仅作展示，不会自动交卷\n"
            "- 写作部分按词数、句数、连接词使用与语法错误四个角度评分"
        )
        if st.button("开始模拟考试", type="primary", key="exam_start"):
            confirm_exam_dialog()
else:
    render_exam_paper()
    if st.button("交卷", type="primary", key="exam_submit", width="stretch"):
        answers = {
            question["id"]: st.session_state.get(f"exam_{question['id']}")
            for section in exam["sections"]
            for question in section["questions"]
        }
        writing_text = st.session_state.get("exam_writing", "")

        if any(value is None for value in answers.values()) and not writing_text.strip():
            st.toast("还没有作答，请完成后交卷", icon="⚠️")
        else:
            with st.spinner("AI 正在阅卷…"):
                graded = tutor_ai.grade_mock_exam(answers, writing_text)
            st.session_state["exam_result"] = graded
            database.add_learning_record(
                user["username"],
                {
                    "module": "模拟试卷",
                    "unit": st.session_state.get("current_unit", ""),
                    "score": graded["total"],
                    "level": tutor_ai.mastery_level(graded["total"]),
                },
            )
            st.rerun()
