"""plotly 绘图组件：四维能力雷达图、学习进度统计图。

配色为单系列方案（浅色 #2a78d6 / 深色 #3987e5），均已通过对比度与色盲
可辨性校验；深色模式使用专门为该表面挑选的色阶，而不是简单反色。
"""

from __future__ import annotations

import plotly.graph_objects as go

import streamlit as st

# 图表调色板（按主题切换，避免自动反转导致对比度不足）
_PALETTE = {
    "light": {
        "series": "#2a78d6",
        "fill": "rgba(42, 120, 214, 0.18)",
        "ink": "#0b0b0b",
        "ink_secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
    },
    "dark": {
        "series": "#3987e5",
        "fill": "rgba(57, 135, 229, 0.24)",
        "ink": "#ffffff",
        "ink_secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
    },
}

_EXCELLENT_LINE = 85  # 优秀线


def _is_dark() -> bool:
    """判断当前主题，取不到时按浅色处理。"""
    try:
        return st.context.theme.type == "dark"
    except Exception:
        try:
            return st.get_option("theme.base") == "dark"
        except Exception:
            return False


def _palette() -> dict:
    return _PALETTE["dark" if _is_dark() else "light"]


def _base_layout(colors: dict, height: int = 360) -> dict:
    """统一的图表骨架：透明背景 + 弱化网格，跟随应用主题。"""
    return {
        "height": height,
        "margin": {"l": 40, "r": 40, "t": 40, "b": 30},
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "system-ui, -apple-system, 'Segoe UI', sans-serif",
                 "size": 13, "color": colors["ink_secondary"]},
        "showlegend": False,
        "hoverlabel": {"font": {"size": 13}},
    }


def render_ability_radar(vocab: int, grammar: int, discourse: int, writing: int) -> go.Figure:
    """四维能力雷达图：词汇能力 / 句法语法 / 语篇理解 / 写作输出。

    返回值直接交给 st.plotly_chart 渲染。
    """
    colors = _palette()
    categories = ["词汇能力", "句法语法", "语篇理解", "写作输出"]
    values = [int(vocab), int(grammar), int(discourse), int(writing)]

    figure = go.Figure()
    figure.add_trace(
        go.Scatterpolar(
            r=values + values[:1],
            theta=categories + categories[:1],
            mode="lines+markers+text",
            name="能力得分",
            line={"color": colors["series"], "width": 2},
            marker={"color": colors["series"], "size": 9,
                    "line": {"color": colors["ink"], "width": 0}},
            fill="toself",
            fillcolor=colors["fill"],
            # 只在 4 个真实顶点上直接标注数值，闭合点不重复标注
            text=[f"{value}" for value in values] + [""],
            textposition="top center",
            textfont={"size": 12, "color": colors["ink"]},
            cliponaxis=False,
            hovertemplate="%{theta}：%{r} 分<extra></extra>",
        )
    )
    figure.update_layout(
        **_base_layout(colors, height=380),
        polar={
            "bgcolor": "rgba(0,0,0,0)",
            "radialaxis": {
                "range": [0, 100],
                "showticklabels": False,
                "gridcolor": colors["grid"],
                "gridwidth": 1,
                "linecolor": colors["axis"],
                "layer": "below traces",
            },
            "angularaxis": {
                "gridcolor": colors["grid"],
                "linecolor": colors["axis"],
                "tickfont": {"size": 13, "color": colors["ink_secondary"]},
                "layer": "below traces",
            },
        },
    )
    return figure


def render_progress_chart(records: list[dict], height: int = 320) -> go.Figure:
    """学习进度统计图：最近若干次练习得分柱状图，并标出优秀线。

    records 为 database.get_learning_records() 的返回值（最新在前）。
    """
    colors = _palette()
    recent = list(reversed(records[:8]))  # 取最近 8 条，按时间正序排列

    if not recent:
        figure = go.Figure()
        figure.update_layout(**_base_layout(colors, height=height))
        figure.update_xaxes(visible=False)
        figure.update_yaxes(visible=False)
        figure.add_annotation(
            text="还没有学习记录，先去完成一次预习或复习练习吧",
            showarrow=False,
            font={"size": 13, "color": colors["muted"]},
            xref="paper", yref="paper", x=0.5, y=0.5,
        )
        return figure

    labels = [record.get("module", "练习") for record in recent]
    scores = [int(record.get("score", 0)) for record in recent]
    hover = [
        f"{record.get('module', '练习')}｜{record.get('unit', '')}<br>"
        f"得分 {int(record.get('score', 0))} 分｜{record.get('level', '')}<br>"
        f"{record.get('time', '')}"
        for record in recent
    ]

    figure = go.Figure(
        go.Bar(
            x=labels,
            y=scores,
            marker={"color": colors["series"], "line": {"width": 0}},
            width=0.55,
            text=scores,
            textposition="outside",
            textfont={"size": 12, "color": colors["ink"]},
            cliponaxis=False,
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover,
            name="练习得分",
        )
    )
    figure.update_layout(**_base_layout(colors, height=height))
    figure.update_xaxes(showgrid=False, linecolor=colors["axis"],
                        tickfont={"size": 12, "color": colors["ink_secondary"]})
    figure.update_yaxes(range=[0, 108], showgrid=True, gridcolor=colors["grid"],
                        zeroline=False, showticklabels=False,
                        title=None)
    figure.add_shape(
        type="line", xref="paper", x0=0, x1=1, y0=_EXCELLENT_LINE, y1=_EXCELLENT_LINE,
        line={"color": colors["muted"], "width": 1, "dash": "dot"},
    )
    figure.add_annotation(
        xref="paper", x=1, y=_EXCELLENT_LINE, text=f"优秀线 {_EXCELLENT_LINE}",
        showarrow=False, xanchor="right", yanchor="bottom",
        font={"size": 11, "color": colors["muted"]},
    )
    return figure
