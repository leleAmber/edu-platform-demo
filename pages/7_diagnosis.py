"""学情诊断：四维能力雷达图 + 诊断摘要 + 错题归因（VIP 专属）。"""

from __future__ import annotations

import streamlit as st

from components import cards, charts
from core import auth, database, tutor_ai, vip

user = auth.require_login()

# VIP 权限拦截：非会员直接弹出拦截弹窗
if not vip.check_vip_permission():
    st.stop()

st.title("📊 学情诊断")
st.caption("基于你的练习与批改记录，从词汇、句法、语篇、写作四个维度给出诊断。")

analysis = tutor_ai.error_analysis()

column_chart, column_summary = st.columns([1, 1], gap="large")

# --------------------------------------------------------------------------- #
# 左栏：四维能力雷达图
# --------------------------------------------------------------------------- #
with column_chart:
    st.subheader("四维能力雷达图")
    figure = charts.render_ability_radar(
        analysis["vocab"], analysis["grammar"], analysis["discourse"], analysis["writing"]
    )
    st.plotly_chart(figure, width="stretch", theme=None)

# --------------------------------------------------------------------------- #
# 右栏：诊断摘要
# --------------------------------------------------------------------------- #
with column_summary:
    st.subheader("学情诊断摘要")

    col_strong, col_weak = st.columns(2)
    col_strong.metric("优势维度", analysis["strongest"], border=True)
    col_weak.metric("薄弱维度", analysis["weakest"], border=True)

    with st.container(border=True):
        st.markdown("**各维度得分**")
        for key, label in tutor_ai.DIMENSION_LABELS.items():
            st.markdown(f"- {label}：**{analysis[key]}** 分")

    st.markdown("**AI 学习改进建议**")
    for index, suggestion in enumerate(analysis["suggestions"], 1):
        st.markdown(f"**{index}.** {suggestion}")

    st.caption(f"本次诊断基于最近 {analysis['sample_count']} 条学习记录，平均分 {analysis['average']} 分。")

st.divider()

# --------------------------------------------------------------------------- #
# 错题归因
# --------------------------------------------------------------------------- #
st.subheader("错题归因")
st.caption("四个维度的错题占比，占比越高说明该维度越需要优先突破。")

tag_columns = st.columns(4)
for index, (dimension, ratio) in enumerate(analysis["error_ratio"].items()):
    with tag_columns[index]:
        with st.container(border=True):
            st.markdown(f"**{dimension}**")
            st.markdown(f"### {ratio}%")
            cards.status_tag(
                "重点突破" if ratio >= 30 else ("需要关注" if ratio >= 20 else "保持即可"),
                "warn" if ratio >= 30 else ("info" if ratio >= 20 else "success"),
            )

st.markdown("**错题占比明细**")
for dimension, ratio in analysis["error_ratio"].items():
    st.progress(min(ratio, 100) / 100, text=f"{dimension}　{ratio}%")

st.divider()

# --------------------------------------------------------------------------- #
# 学习进度
# --------------------------------------------------------------------------- #
st.subheader("学习进度统计")
records = database.get_learning_records(user["username"])
st.plotly_chart(charts.render_progress_chart(records), width="stretch", theme=None)
if records:
    st.caption(f"共记录 {len(records)} 次练习，最新一次得分 {records[0].get('score', '-')} 分。")
