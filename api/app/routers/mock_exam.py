"""模拟试卷（VIP 专属）。

组卷结果存在用户会话缓存里：同一场考试内取卷与判卷必须是同一张卷，
否则学生对不上答案。批改时 grade_mock_exam 会自己回缓存取那份带答案的卷，
不依赖客户端回传。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core import database, tutor_ai  # noqa: E402

from .. import jobs as job_store  # noqa: E402
from ..deps import require_vip  # noqa: E402
from ..schemas import MockExamGradeRequest  # noqa: E402
from ..serialize import public_exam  # noqa: E402

router = APIRouter(prefix="/mock-exam", tags=["模拟试卷"])

VipUser = Depends(require_vip)


@router.get("", summary="获取模拟试卷（VIP）")
def get_exam(
    book: str = Query(..., max_length=50),
    refresh: bool = Query(False, description="true 则重新随机组一套卷"),
    user: dict = VipUser,
) -> dict:
    """客观题的 answer / explain 已剥离，只下发题面与选项。"""
    exam = tutor_ai.get_mock_exam(book, refresh=refresh)
    return public_exam(exam)


@router.post("/grade", summary="交卷并批改（VIP，异步）")
def grade(payload: MockExamGradeRequest, user: dict = VipUser) -> dict:
    """返回 job_id；轮询 /jobs/{job_id} 取评分结果。

    写作部分会调用大模型评分，耗时较长，因此走异步任务。
    """
    if not payload.answers and not any(payload.writings.values()):
        raise HTTPException(status_code=400, detail="还没有作答，请完成后交卷")

    def work() -> dict:
        graded = tutor_ai.grade_mock_exam(payload.book, payload.answers, payload.writings)
        database.add_learning_record(
            user["username"],
            {
                "module": "模拟试卷",
                "unit": f"{payload.book}·模拟卷",
                "score": graded["total"],
                "level": tutor_ai.mastery_level(graded["total"]),
            },
        )
        return graded

    return {"job_id": job_store.submit("mock-exam-grade", user, work)}
