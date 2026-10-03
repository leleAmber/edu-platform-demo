"""客服留言：学生提交留言、查看自己的留言与回复。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core import database  # noqa: E402

from ..deps import current_user  # noqa: E402
from ..schemas import MessageRequest  # noqa: E402

router = APIRouter(prefix="/messages", tags=["客服"])

CurrentUser = Depends(current_user)


@router.post("", summary="提交留言")
def create_message(payload: MessageRequest, user: dict = CurrentUser) -> dict:
    message = database.add_message({"username": user["username"], "content": payload.content})
    return {"ok": True, "message": "留言已提交，我们会尽快回复", "record": message}


@router.get("", summary="我的留言与回复")
def my_messages(user: dict = CurrentUser) -> dict:
    username = user["username"]
    mine = [item for item in database.get_all_messages() if item.get("username") == username]
    return {
        "messages": mine,
        "count": len(mine),
        "pending": sum(1 for item in mine if not item.get("is_replied")),
    }
