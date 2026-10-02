"""模拟试卷：VIP 专属。完整新高考题型（阅读理解/七选五/完形填空/语法填空/应用文写作/读后续写），
只抽取当前选中教材的题库题目。"""

from __future__ import annotations

import streamlit as st

from components import book_selector
from core import auth, database, tutor_ai, vip

user = auth.require_login()

# VIP 权限拦截：非会员直接弹出拦截弹窗，无法查看试卷内容
if not vip.check_vip_permission():
    st.stop()

st.title("📝 模拟试卷")

book = book_selector.render_book_selector()
exam = tutor_ai.get_mock_exam(book)


def _objective_question_ids(paper: dict) -> list[str]:
    """收集一份试卷里所有客观题的 id（用于重置答题状态）。"""
    ids = []
    for section in paper["sections"]:
        if section["key"].startswith("writing"):
            continue
        if section.get("passages"):
            for p in section["passages"]:
                ids.extend(q["id"] for q in p["questions"])
        else:
            ids.extend(q["id"] for q in section["questions"])
    return ids


def _clear_answers(paper: dict) -> None:
    """清空一份试卷的作答状态（客观题选项 + 两篇写作）。"""
    for qid in _objective_question_ids(paper):
        st.session_state.pop(f"exam_{qid}", None)
    st.session_state.pop("exam_writing_practical", None)
    st.session_state.pop("exam_writing_continuation", None)


def _new_paper() -> None:
    """重新随机组一套卷，并回到「开始前须知」的未开考状态。"""
    _clear_answers(exam)  # 先按旧卷清作答，见下方 id 重名说明
    tutor_ai.get_mock_exam(book, refresh=True)
    st.session_state["exam_started"] = False
    st.session_state.pop("exam_result", None)


# 中途换教材等于换卷。题目的 id 是按位置编的（r1..r8 / s1..s5 / c1..c10 / g1..g10），
# 新旧卷 id 完全重名，不作废旧作答的话，上一册的选择会被当成这一册的答案计入批改。
if st.session_state.get("exam_book") != book:
    _clear_answers(exam)
    st.session_state["exam_book"] = book
    st.session_state["exam_started"] = False
    st.session_state.pop("exam_result", None)

st.caption(f"{exam['title']}｜当前教材：{book}｜满分 100 分｜建议用时 {exam['duration']} 分钟")


@st.dialog("开始模拟考试", width="small")
def confirm_exam_dialog() -> None:
    st.write("模拟考试开始，计时功能为演示版本。")
    st.caption("交卷后系统会自动评分，并给出各题型得分与学习建议。")
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
            key = section["key"]

            # 写作：应用文 / 读后续写
            if key == "writing_practical":
                st.markdown(f"**题目**：{section['prompt']}")
                for requirement in section["requirements"]:
                    st.markdown(f"- {requirement}")
                st.text_area("应用文作答区", key="exam_writing_practical", height=200,
                             placeholder="在此写下你的应用文…", label_visibility="collapsed")
                continue

            if key == "writing_continuation":
                if section.get("passage"):
                    st.write(section["passage"])
                    st.divider()
                st.markdown(f"**题目**：{section['prompt']}")
                for requirement in section["requirements"]:
                    st.markdown(f"- {requirement}")
                st.text_area("读后续写作答区", key="exam_writing_continuation", height=220,
                             placeholder="在此续写…", label_visibility="collapsed")
                continue

            # 七选五：选项 A~G 在 section 级共享
            if key == "seven_five":
                st.write(section["passage"])
                st.divider()
                st.markdown("**选项**：")
                for i, opt in enumerate(section["options"]):
                    st.markdown(f"{chr(65 + i)}. {opt}")
                st.divider()
                for q in section["questions"]:
                    st.markdown(f"**{q['question']}**")
                    st.radio(q["id"], section["options"], key=f"exam_{q['id']}", label_visibility="collapsed")
                continue

            # 阅读理解：多篇 passage
            if key == "reading":
                for p in section["passages"]:
                    st.write(p["passage"])
                    st.divider()
                    for q in p["questions"]:
                        st.markdown(f"**{q['question']}**")
                        st.radio(q["id"], q["options"], key=f"exam_{q['id']}", label_visibility="collapsed")
                continue

            # 完形填空：每空 4 选项
            if key == "cloze":
                st.write(section["passage"])
                st.divider()
                for q in section["questions"]:
                    st.markdown(f"**{q['question']}**")
                    st.radio(q["id"], q["options"], key=f"exam_{q['id']}", label_visibility="collapsed")
                continue

            # 语法填空：自由填词
            if key == "grammar_blank":
                st.write(section["passage"])
                st.divider()
                for q in section["questions"]:
                    st.text_input(q["question"], key=f"exam_{q['id']}")


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
            if item["explain"]:
                st.caption(f"解析：{item['explain']}")

    with st.expander("查看写作点评", expanded=True):
        for note in result["writing_notes"]:
            st.markdown(f"- {note}")

    if st.button("再考一次（换新卷）", key="exam_restart"):
        _new_paper()
        st.rerun()


result = st.session_state.get("exam_result")
if result:
    render_exam_result(result)
elif not st.session_state.get("exam_started"):
    with st.container(border=True):
        st.markdown("#### 开始前须知")
        st.markdown(
            "- 试卷含阅读理解、七选五、完形填空、语法填空、应用文写作、读后续写六个题型，满分 100 分\n"
            "- 题型种类与出题逻辑贴近新高考，仅题量缩减\n"
            "- 演示版本的计时功能仅作展示，不会自动交卷\n"
            "- 写作部分按词数、句数、连接词使用与语法错误四个角度评分"
        )
        col_start, col_reshuffle = st.columns([2, 1])
        if col_start.button("开始模拟考试", type="primary", key="exam_start", width="stretch"):
            confirm_exam_dialog()
        if col_reshuffle.button("换一套试卷", key="exam_reshuffle", width="stretch"):
            _new_paper()
            st.toast("已从当前教材题库重新随机组卷", icon="🔀")
            st.rerun()
else:
    render_exam_paper()
    if st.button("交卷", type="primary", key="exam_submit", width="stretch"):
        answers = {
            qid: st.session_state.get(f"exam_{qid}")
            for qid in _objective_question_ids(exam)
        }
        writings = {
            "writing_practical": st.session_state.get("exam_writing_practical", ""),
            "writing_continuation": st.session_state.get("exam_writing_continuation", ""),
        }

        if all(value is None for value in answers.values()) and not any(writings.values()):
            st.toast("还没有作答，请完成后交卷", icon="⚠️")
        else:
            with st.spinner("AI 正在阅卷…"):
                graded = tutor_ai.grade_mock_exam(book, answers, writings)
            st.session_state["exam_result"] = graded
            database.add_learning_record(
                user["username"],
                {
                    "module": "模拟试卷",
                    "unit": f"{book}·模拟卷",
                    "score": graded["total"],
                    "level": tutor_ai.mastery_level(graded["total"]),
                },
            )
            st.rerun()
