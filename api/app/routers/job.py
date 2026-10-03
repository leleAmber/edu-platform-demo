"""异步任务查询：客户端轮询这个接口取批改结果。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from .. import jobs as job_store  # noqa: E402
from ..deps import current_user  # noqa: E402

router = APIRouter(prefix="/jobs", tags=["异步任务"])

CurrentUser = Depends(current_user)

# 建议客户端轮询间隔（秒）。大模型批改一般 10~30 秒，
# 2 秒一次既不迟钝也不会把服务端打满。
POLL_INTERVAL_SECONDS = 2


@router.get("/{job_id}", summary="查询任务状态")
def get_job(job_id: str, response: Response, user: dict = CurrentUser) -> dict:
    """status: pending / done / error。

    任务不存在或不属于当前用户时返回 404（不区分这两种情况，避免被用来探测
    别人的 job_id 是否存在）。
    """
    job = job_store.get(job_id, user["username"])
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在或已过期")

    if job["status"] == "pending":
        response.headers["Retry-After"] = str(POLL_INTERVAL_SECONDS)

    return {
        "job_id": job["job_id"],
        "kind": job["kind"],
        "status": job["status"],
        "poll_interval": POLL_INTERVAL_SECONDS,
        "result": job["result"],
        "error": job["error"],
    }
