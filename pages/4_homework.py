"""作业中心：键盘输入或上传图片识别题目，AI 自动批改（大模型优先，本地规则引擎兜底）。

支持作文 / 选择题 / 填空题。免费用户只看到总分与对错数量，VIP 才展示逐题解析。
"""

from __future__ import annotations

import streamlit as st

from components.cards import goto_page
from core import auth, database, llm, ocr, tutor_ai, vip

PAGE_MEMBER = "pages/6_membership.py"
PAGE_DIAGNOSIS = "pages/7_diagnosis.py"

user = auth.require_login()
is_vip = vip.is_vip(user)

st.title("✍️ 作业中心")
st.caption("键盘输入或上传作业图片，AI 自动识别题目并批改（作文 / 选择题 / 填空题均可）。")

# OCR 识别结果回填到输入框
if st.session_state.pop("_ocr_to_fill", False):
    st.session_state["homework_text"] = st.session_state.pop("_ocr_text", "")

column_input, column_result = st.columns([1, 1], gap="large")

# --------------------------------------------------------------------------- #
# 左栏：作业录入（键盘 + 图片）
# --------------------------------------------------------------------------- #
with column_input:
    st.subheader("作业录入")
    homework_text = st.text_area(
        "作业内容",
        key="homework_text",
        height=280,
        placeholder="键盘粘贴作业，或上传图片后点「识别图片」自动填入",
    )
    st.caption("支持打印题 + 手写答案的照片，也可直接粘贴文字。")
    if st.session_state.get("homework_from_ocr"):
        st.caption("⚠️ 图片识别结果可能有误、顺序可能错乱，批改前请先检查并修正上面的内容。")

    st.divider()
    st.markdown("**📷 上传作业图片**（最多 5 张）")
    st.caption("拍照小贴士：正对纸张、光线充足、避免反光和阴影，字写深一点识别更准。")
    uploaded = st.file_uploader(
        "选择图片",
        type=["png", "jpg", "jpeg"],
        key="homework_upload",
        label_visibility="collapsed",
        accept_multiple_files=True,
    )

    # 摄像头默认不唤起，点按钮才开启，避免一进页面就申请摄像头权限；拍完可关闭
    camera = None
    if not st.session_state.get("show_camera"):
        if st.button("📸 拍照上传", key="homework_camera_toggle", width="stretch"):
            st.session_state["show_camera"] = True
    else:
        camera = st.camera_input("拍照", key="homework_camera")
        if st.button("✖️ 关闭摄像头", key="homework_camera_close", width="stretch"):
            st.session_state["show_camera"] = False
            st.session_state.pop("homework_camera", None)

    # 汇总所有图片（上传 + 拍照），最多 5 张，超出的给出提示并忽略
    images = list(uploaded or [])
    if camera is not None:
        images.append(camera)
    if len(images) > 5:
        st.warning(f"最多只能识别 5 张图片，当前共 {len(images)} 张，仅识别前 5 张。")
        images = images[:5]

    if st.button("🔍 识别图片", key="homework_ocr", width="stretch"):
        if not images:
            st.toast("请先上传或拍摄作业图片", icon="⚠️")
        elif not ocr.is_available() and not llm.vision_available():
            st.toast("识别组件不可用：本地 OCR 未安装且未配置视觉大模型", icon="⚠️")
        else:
            with st.spinner(f"正在识别 {len(images)} 张图片…"):
                parts = []
                for img in images:
                    raw = img.getvalue()
                    # AI 优先：先用视觉大模型识别，识别不到再退回本地 OCR
                    text_part = ""
                    if llm.vision_available():
                        text_part = (llm.recognize_image(raw) or "").strip()
                    if not text_part:
                        text_part = ocr.recognize(raw).strip()
                    if text_part:
                        parts.append(text_part)
                text = "\n\n".join(parts)
            if not text:
                st.toast("未识别到文字，请换更清晰的图片或手动输入", icon="⚠️")
            else:
                st.session_state["_ocr_text"] = text
                st.session_state["_ocr_to_fill"] = True
                st.session_state["homework_from_ocr"] = True
                st.rerun()

    st.divider()
    if st.button("提交 AI 批改", type="primary", key="homework_submit", width="stretch"):
        if len(homework_text.strip()) < 10:
            st.toast("内容太短了，请至少输入一个完整句子或一道题", icon="⚠️")
        else:
            with st.spinner("AI 正在批改（逐句并行，约 10~30 秒）…"):
                result = tutor_ai.grade_homework(homework_text)
            st.session_state["homework_result"] = result

            # 兜底模式（选择/填空且未配置大模型）无法判分，不写入学习记录，避免把 0 分计入学情
            if result["mode"] == "llm" or result["total_score"] > 0:
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

    if not result:
        st.info("提交作业后，这里会显示 AI 批改结果。")
    else:
        st.caption(f"批改引擎：{result.get('source', '')}")
        if result.get("note"):
            st.info(result["note"])

        col_total, col_right, col_wrong = st.columns(3)
        col_total.metric("总分", f"{result['total_score']} 分")
        col_right.metric("答对", result["right_count"], border=True)
        col_wrong.metric("待修改", result["wrong_count"], border=True)

        if not is_vip:
            st.info("开通 VIP 查看逐题解析与修改建议。")
            if st.button("前往会员中心开通", key="homework_upgrade", width="stretch"):
                goto_page(PAGE_MEMBER)
        else:
            if result.get("comment"):
                st.markdown(f"**AI 评语**：{result['comment']}")

            details = result.get("details", [])
            if not details:
                st.success("未检测到明显问题，继续保持！")
            else:
                st.caption(f"共 {len(details)} 条，点击展开查看逐题解析。")
                for item in details:
                    status = item.get("is_right")
                    if status is True:
                        label = f"第 {item['index']} 题｜✅ 正确"
                    elif status is False:
                        label = f"第 {item['index']} 题｜❌ {item.get('error_type') or '有误'}"
                    else:
                        label = f"第 {item['index']} 题｜❓ 待核对"
                    with st.expander(label):
                        if item.get("question"):
                            st.markdown(f"**题目/原句**：{item['question']}")
                        if item.get("your_answer"):
                            st.markdown(f"**你的作答**：{item['your_answer']}")
                        if item.get("correct_answer"):
                            st.markdown(f"**参考答案/修改后**：{item['correct_answer']}")
                        if item.get("explain"):
                            st.markdown(f"**解析**：{item['explain']}")

            error_types = result.get("error_types") or {}
            if error_types:
                st.markdown("**错误类型分布**")
                for error_type, count in sorted(error_types.items(), key=lambda pair: -pair[1]):
                    st.markdown(f"- {error_type}：{count} 处")

            if st.button("查看四维能力评估", key="homework_to_diagnosis", width="stretch"):
                goto_page(PAGE_DIAGNOSIS)
