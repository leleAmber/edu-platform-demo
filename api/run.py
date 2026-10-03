"""开发启动脚本：python run.py

生产环境用 uvicorn 直接起（见 README）：
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

--workers 目前必须是 1：异步任务的结果存在进程内存里（app/jobs.py），
多 worker 时轮询可能落到另一个进程，查不到刚提交的任务。
"""

from __future__ import annotations

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=os.environ.get("API_RELOAD", "1") == "1",
        workers=1,
    )
