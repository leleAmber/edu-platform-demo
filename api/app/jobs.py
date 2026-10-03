"""异步任务：给耗时的大模型接口用。

为什么需要：批改一次作业要 10~30 秒，视觉识别更久。同步返回会有两个问题：
1. 微信云托管 callContainer 单次调用硬限 15 秒，必然超时；
2. 手机端干等 30 秒白屏转圈，体验很差。

所以批改类接口一律「提交拿 job_id → 客户端轮询」，接口本身 200ms 内返回。
轮询间隔由客户端控制，每次请求都很短，15 秒限制就不再是问题。

存储是进程内的：单 worker 部署足够。多 worker 时轮询可能落到另一个进程查不到 job，
那种情况下要换成 Redis 或数据库——见 README「已知限制」。
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from collections import OrderedDict
from typing import Callable

from core import runtime  # noqa: E402

JOB_TTL_SECONDS = 1800          # 结果保留 30 分钟，够客户端取走
MAX_JOBS = 1000                 # 上限，防止长期运行内存无界增长

_JOBS: "OrderedDict[str, dict]" = OrderedDict()
_LOCK = threading.Lock()


def _prune_locked() -> None:
    """清理过期任务（调用方需持锁）。"""
    now = time.time()
    expired = [jid for jid, job in _JOBS.items() if now - job["created_at"] > JOB_TTL_SECONDS]
    for jid in expired:
        _JOBS.pop(jid, None)
    while len(_JOBS) > MAX_JOBS:
        _JOBS.popitem(last=False)


def submit(kind: str, user: dict, work: Callable[[], object]) -> str:
    """提交一个后台任务，立即返回 job_id。

    work 会在线程里执行，并绑定提交者的用户上下文——core/ 内部的
    auth.get_current_user() 在 worker 线程里同样要能拿到人。
    """
    job_id = uuid.uuid4().hex
    username = str(user.get("username", ""))

    with _LOCK:
        _prune_locked()
        _JOBS[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "username": username,
            "status": "pending",
            "result": None,
            "error": None,
            "created_at": time.time(),
        }

    def _worker() -> None:
        # 显式绑定上下文：新线程不会自动继承提交方的 ContextVar
        with runtime.api_request(dict(user)):
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001 - 任务失败要如实回报给客户端
                with _LOCK:
                    job = _JOBS.get(job_id)
                    if job is not None:
                        job["status"] = "error"
                        job["error"] = str(exc) or exc.__class__.__name__
                traceback.print_exc()
            else:
                with _LOCK:
                    job = _JOBS.get(job_id)
                    if job is not None:
                        job["status"] = "done"
                        job["result"] = result

    threading.Thread(target=_worker, name=f"job-{kind}-{job_id[:8]}", daemon=True).start()
    return job_id


def get(job_id: str, username: str) -> dict | None:
    """取任务状态。只返回属于该用户的任务，越权查询一律当作不存在。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["username"] != username:
            return None
        return {
            "job_id": job["job_id"],
            "kind": job["kind"],
            "status": job["status"],
            "result": job["result"],
            "error": job["error"],
        }


def pending_count(username: str) -> int:
    """该用户未完成的任务数，用于前端判断是否需要继续轮询。"""
    with _LOCK:
        return sum(
            1 for job in _JOBS.values()
            if job["username"] == username and job["status"] == "pending"
        )
