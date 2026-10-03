"""学情诊断（VIP 专属）：四维能力、错题归因、学习进度。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core import database, tutor_ai  # noqa: E402

from ..deps import require_vip  # noqa: E402

router = APIRouter(tags=["学情诊断"])

VipUser = Depends(require_vip)


@router.get("/diagnosis", summary="四维能力诊断（VIP）")
def diagnosis(user: dict = VipUser) -> dict:
    """词汇 / 句法 / 语篇 / 写作四维得分、错题占比与改进建议。

    结果由「用户名 + 学习记录条数 + 总分」做种子生成，同一批学习记录下
    反复请求结果稳定，不会每次刷新都变——对应网页版的 _stable_seed。
    """
    analysis = tutor_ai.error_analysis()
    dimension_labels = tutor_ai.DIMENSION_LABELS
    records = database.get_learning_records(user["username"])
    return {
        "dimensions": {key: analysis[key] for key in dimension_labels},
        "dimension_labels": dict(dimension_labels),
        "strongest": analysis["strongest"],
        "weakest": analysis["weakest"],
        "error_ratio": analysis["error_ratio"],
        "suggestions": analysis["suggestions"],
        "average": analysis["average"],
        "sample_count": analysis["sample_count"],
        # 雷达图与进度图的数据一并给出，客户端（ECharts）直接画
        "radar": {
            "categories": [dimension_labels[key] for key in dimension_labels],
            "values": [analysis[key] for key in dimension_labels],
            "max": 100,
            "excellent_line": 85,
        },
        "progress": _progress(records),
    }


def _progress(records: list[dict]) -> dict:
    """学习进度柱状图数据：最近 8 次，按时间正序（与网页版 charts.render_progress_chart 一致）。"""
    recent = list(reversed(records[:8]))
    return {
        "labels": [r.get("module", "练习") for r in recent],
        "values": [int(r.get("score", 0) or 0) for r in recent],
        "details": [
            {
                "module": r.get("module", "练习"),
                "unit": r.get("unit", ""),
                "score": int(r.get("score", 0) or 0),
                "level": r.get("level", ""),
                "time": r.get("time", ""),
            }
            for r in recent
        ],
        "excellent_line": 85,
        "total_count": len(records),
    }
