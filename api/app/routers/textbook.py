"""教材：书目录、单元列表、单元内容（含预习/复习练习，题目已脱敏）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core import textbook, tutor_ai  # noqa: E402

from ..deps import current_user  # noqa: E402
from ..serialize import public_unit_content  # noqa: E402

router = APIRouter(prefix="/textbooks", tags=["教材"])

CurrentUser = Depends(current_user)


@router.get("", summary="教材目录")
def list_books(user: dict = CurrentUser) -> dict:
    """7 册教材的 key / name / grade / units。"""
    return {"books": textbook.get_books()}


@router.get("/{book}/units", summary="某册的单元列表")
def list_units(book: str, user: dict = CurrentUser) -> dict:
    units = textbook.get_units(book)
    if not units:
        raise HTTPException(status_code=404, detail=f"教材不存在或暂无单元：{book}")
    meta = textbook.get_book_meta(book) or {}
    return {"book": book, "name": meta.get("name", ""), "grade": meta.get("grade", ""), "units": units}


@router.get("/{book}/units/{unit}", summary="单元内容")
def unit_content(book: str, unit: str, user: dict = CurrentUser) -> dict:
    """单元主题、单词、核心句型、预习与复习练习。

    练习题目已去掉 answer / explain —— 答案只留在服务端，批改时由
    grade_quiz 自己回缓存取，客户端拿不到。
    """
    content = tutor_ai.get_unit_content(book, unit)
    return public_unit_content(content)


@router.get("/{book}/units/{unit}/refresh-quiz", summary="换一组练习题")
def refresh_quiz(
    book: str,
    unit: str,
    quiz_type: str = Query(..., pattern="^(preview|review)$"),
    user: dict = CurrentUser,
) -> dict:
    """清掉会话缓存，下次取题重新随机抽取（对应网页版的「换一批」）。"""
    tutor_ai.refresh_unit_quiz(book, unit, quiz_type)
    content = tutor_ai.get_unit_content(book, unit)
    return {"quiz": public_unit_content(content).get(f"{quiz_type}_quiz", [])}
