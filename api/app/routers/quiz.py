"""预习 / 复习：批改练习、生成学习计划、学习记录。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core import database, tutor_ai  # noqa: E402

from ..deps import current_user  # noqa: E402
from ..schemas import QuizGradeRequest, StudyPlanRequest  # noqa: E402

router = APIRouter(tags=["预习复习"])

CurrentUser = Depends(current_user)

_MODULE_BY_TYPE = {"preview": "课本预习", "review": "课本复习"}


@router.post("/quiz/grade", summary="批改预习/复习练习")
def grade_quiz(payload: QuizGradeRequest, user: dict = CurrentUser) -> dict:
    """answers 形如 {"0": "选项文本", ...}，键是题目下标。

    批改在服务端完成，用的还是那份带答案的会话缓存，与下发题目时是同一组题——
    这也是抽题缓存必须挂在用户身上、不能挂模块全局的原因。
    """
    result = tutor_ai.grade_quiz(payload.book, payload.unit, payload.quiz_type, payload.answers)

    mastery, level = tutor_ai.get_mastery_score(
        seed=f"{payload.book}-{payload.unit}-{payload.quiz_type}-{result['correct_count']}",
        base=result["score"],
    )
    result.update({"unit": payload.unit, "mastery": mastery, "level": level})

    database.add_learning_record(
        user["username"],
        {
            "module": _MODULE_BY_TYPE[payload.quiz_type],
            "unit": f"{payload.book}·{payload.unit}",
            "score": result["score"],
            "level": level,
        },
    )
    return result


@router.post("/study-plan", summary="生成学习计划（VIP）")
def study_plan(payload: StudyPlanRequest, user: dict = CurrentUser) -> dict:
    """预习计划 3 天，复习计划 7 天；具体文案由 core.gen_study_plan 生成。"""
    plan = tutor_ai.gen_study_plan(payload.plan_type, payload.unit, payload.book)
    if not plan:
        raise HTTPException(status_code=400, detail="无法生成学习计划，请先完成一次练习")
    return plan


@router.get("/records", summary="学习记录")
def records(
    limit: int = Query(20, ge=1, le=100),
    user: dict = CurrentUser,
) -> dict:
    """最近的学习记录（最新在前）。"""
    items = database.get_learning_records(user["username"], limit=limit)
    return {"records": items, "count": len(items)}
