"""管理后台：用户、订单、留言统计与回复。

网页版的后台在学生端之外单独成页（pages/8_admin.py），移动端不迁移后台 UI，
但接口保留——需要时可以用网页版管理，或用任意 HTTP 客户端调这些接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core import database  # noqa: E402

from ..deps import require_admin  # noqa: E402
from ..schemas import ReplyRequest  # noqa: E402
from ..serialize import user_payload  # noqa: E402

router = APIRouter(prefix="/admin", tags=["管理后台"])

AdminUser = Depends(require_admin)


@router.get("/stats", summary="后台概览")
def stats(user: dict = AdminUser) -> dict:
    users = database.get_all_users()
    orders = database.get_all_orders()
    messages = database.get_all_messages()
    return {
        "user_count": len(users),
        "student_count": sum(1 for item in users if item.get("role") == "student"),
        "order_count": len(orders),
        "income": round(sum(float(item.get("amount", 0) or 0) for item in orders), 2),
        "pending_messages": sum(1 for item in messages if not item.get("is_replied")),
    }


@router.get("/users", summary="用户列表")
def list_users(
    q: str | None = Query(None, max_length=100, description="按用户名或邮箱模糊搜索"),
    user: dict = AdminUser,
) -> dict:
    users = [user_payload(item) | {"created_at": item.get("created_at")}
             for item in database.get_all_users()]
    if q:
        needle = q.strip().lower()
        users = [
            item for item in users
            if needle in item["username"].lower() or needle in (item["email"] or "").lower()
        ]
    return {"users": users, "count": len(users)}


@router.get("/orders", summary="订单列表")
def list_orders(user: dict = AdminUser) -> dict:
    orders = database.get_all_orders()
    total = sum(float(item.get("amount", 0) or 0) for item in orders)
    return {"orders": orders, "count": len(orders), "total_amount": round(total, 2)}


@router.get("/messages", summary="留言列表")
def list_messages(user: dict = AdminUser) -> dict:
    messages = database.get_all_messages()
    return {
        "messages": messages,
        "count": len(messages),
        "pending": sum(1 for item in messages if not item.get("is_replied")),
    }


@router.post("/messages/{message_id}/reply", summary="回复留言")
def reply_message(message_id: str, payload: ReplyRequest, user: dict = AdminUser) -> dict:
    updated = database.update_message(message_id, payload.reply)
    if not updated:
        raise HTTPException(status_code=404, detail="留言不存在")
    return {"ok": True, "message": "回复已提交", "record": updated}
