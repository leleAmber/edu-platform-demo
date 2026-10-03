"""会员：套餐、模拟支付、订单记录。

支付仍是**模拟支付**（与网页版一致）：不接微信支付/支付宝，不涉及商户资质。
process_payment 只计算到期时间并写订单，不产生任何真实扣款。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from core import database, vip  # noqa: E402

from ..deps import current_user  # noqa: E402
from ..schemas import PurchaseRequest  # noqa: E402
from ..serialize import user_payload  # noqa: E402

router = APIRouter(prefix="/membership", tags=["会员"])

CurrentUser = Depends(current_user)


@router.get("/plans", summary="套餐与权益对比")
def plans(user: dict = CurrentUser) -> dict:
    return {
        "plans": [vip.PLANS[name] for name in vip.PLAN_ORDER],
        "feature_matrix": [
            {"feature": feature, "free": bool(free), "vip": bool(paid)}
            for feature, free, paid in vip.FEATURE_MATRIX
        ],
        "current": user_payload(user),
    }


@router.post("/purchase", summary="开通会员（模拟支付）")
def purchase(payload: PurchaseRequest, user: dict = CurrentUser) -> dict:
    """模拟支付：续费从当前到期时间顺延，不浪费剩余天数。"""
    result = vip.process_payment(user["username"], payload.plan)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", "开通失败"))

    # process_payment 内部刷新的是请求上下文里的用户，这里重新回库取一次，
    # 保证响应里的会员状态是刚写入的最新值
    latest = database.get_user_by_username(user["username"]) or user
    return {**result, "user": user_payload(dict(latest))}


@router.get("/orders", summary="我的消费记录")
def my_orders(user: dict = CurrentUser) -> dict:
    """只返回自己的订单。

    database 层目前只有 get_all_orders()（后台用），这里按用户名过滤。
    订单量级还很小，不值得为它加一个专用查询；量大了再说。
    """
    username = user["username"]
    mine = [order for order in database.get_all_orders() if order.get("username") == username]
    total = sum(float(order.get("amount", 0) or 0) for order in mine)
    return {"orders": mine, "count": len(mine), "total_amount": round(total, 2)}
