"""作业中心：图片识别 + AI 批改。

两个接口都是耗时的（视觉识别与逐句批改十几秒到一分钟），所以一律走异步任务：
提交返回 job_id，客户端轮询 /jobs/{job_id}。这样做的两个理由：
1. 微信云托管 callContainer 单次调用硬限 15 秒，同步返回必然超时；
2. 手机端干等 30 秒白屏，体验很差，改成进度提示更合适。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from core import database, llm, tutor_ai, vip  # noqa: E402

from .. import jobs as job_store  # noqa: E402
from ..deps import current_user  # noqa: E402
from ..schemas import HomeworkGradeRequest  # noqa: E402
from ..serialize import strip_homework_details  # noqa: E402

router = APIRouter(prefix="/homework", tags=["作业"])

CurrentUser = Depends(current_user)

MAX_IMAGES = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024       # 单张 10MB，够手机原图了


@router.post("/recognize", summary="上传作业图片并识别成文字（异步）")
async def recognize(
    files: list[UploadFile] = File(..., description="作业图片，最多 5 张"),
    user: dict = CurrentUser,
) -> dict:
    """返回 job_id；轮询 /jobs/{job_id} 取识别出的文字。

    识别结果只是「草稿」——网页版也会提示用户先核对再提交批改，
    因为视觉模型对手写体的识别难免有错字和错序。
    """
    if not files:
        raise HTTPException(status_code=400, detail="请先上传作业图片")
    if len(files) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"一次最多识别 {MAX_IMAGES} 张图片")
    if not llm.vision_available():
        raise HTTPException(
            status_code=503,
            detail="识别组件不可用：未配置视觉大模型（LLM_VISION_MODEL）",
        )

    # 先把文件读进内存再提交任务：UploadFile 的生命周期只到本次请求结束，
    # 后台线程里再读会拿到已关闭的文件句柄。
    payloads: list[bytes] = []
    for item in files:
        data = await item.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail=f"图片过大（{item.filename}），请压缩后重试")
        if data:
            payloads.append(data)
    if not payloads:
        raise HTTPException(status_code=400, detail="上传的图片为空")

    def work() -> dict:
        parts = []
        for data in payloads:
            text_part = (llm.recognize_image(data) or "").strip()
            if text_part:
                parts.append(text_part)
        return {"text": "\n\n".join(parts), "image_count": len(payloads)}

    return {"job_id": job_store.submit("recognize", user, work)}


@router.post("/grade", summary="提交作业批改（异步）")
def grade(payload: HomeworkGradeRequest, user: dict = CurrentUser) -> dict:
    """返回 job_id；轮询 /jobs/{job_id} 取批改结果。

    免费用户只能拿到总分与对错统计，逐题解析在服务端就被剥掉了——
    内容级门禁必须在服务端做，客户端藏是藏不住的。
    """
    text = (payload.text or "").strip()
    if len(text) < 10:
        raise HTTPException(status_code=400, detail="内容太短了，请至少输入一个完整句子或一道题")

    is_vip = vip.is_vip(user)

    def work() -> dict:
        result = tutor_ai.grade_homework(text)
        # 兜底模式（选择/填空且未配置大模型）无法判分，不写入学习记录，
        # 避免把 0 分计入学情——与网页版逻辑一致
        if result["mode"] == "llm" or result["total_score"] > 0:
            database.add_learning_record(
                user["username"],
                {
                    "module": "作业批改",
                    "unit": f"{payload.book}·{payload.unit}" if payload.book and payload.unit
                            else (payload.unit or ""),
                    "score": result["total_score"],
                    "level": tutor_ai.mastery_level(result["total_score"]),
                },
            )
        return strip_homework_details(result, is_vip=is_vip)

    return {"job_id": job_store.submit("homework-grade", user, work)}
