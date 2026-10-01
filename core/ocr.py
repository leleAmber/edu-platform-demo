"""OCR 层：本地 RapidOCR 识别作业图片文字。

离线、免费，不依赖任何外部服务。模型懒加载为单例，识别失败时返回空字符串，
由调用方降级到键盘输入。RapidOCR 使用 PaddleOCR v3 模型（中英文混排、手写可识别）。
针对手写/拍照场景做了图片预处理与检测参数调优，以提升潦草字迹的识别率。
"""

from __future__ import annotations

import numpy as np

_engine = None

# 手写/拍照调优参数（相对 RapidOCR 默认值）：
# - det_limit_side_len 调大：检测时把图放大到更长边 1280，小字/淡字更容易被框出来；
# - det_box_thresh 调低：保留更淡的文字候选框；
# - det_unclip_ratio 调低：减少文本框外扩，避免相邻手写行/单词粘连；
# - text_score 调低：保留低置信度识别结果（可能带少量噪声，但可在页面里人工再编辑）。
_DET_LIMIT_SIDE_LEN = 1280
_DET_BOX_THRESH = 0.3
_DET_UNCLIP_RATIO = 1.4
_TEXT_SCORE = 0.4


def _get_engine():
    """懒加载 RapidOCR 单例，未安装依赖时返回 None。"""
    global _engine
    if _engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            return None
        try:
            _engine = RapidOCR(
                det_model_path="",  # 传空串表示沿用包内默认检测模型
                det_limit_side_len=_DET_LIMIT_SIDE_LEN,
                det_box_thresh=_DET_BOX_THRESH,
                det_unclip_ratio=_DET_UNCLIP_RATIO,
                text_score=_TEXT_SCORE,
            )
        except Exception:
            # 某些版本参数不被支持时退回默认配置
            _engine = RapidOCR()
    return _engine


def is_available() -> bool:
    """OCR 是否可用（未安装 rapidocr-onnxruntime 时返回 False）。"""
    return _get_engine() is not None


def _preprocess(image_bytes: bytes) -> np.ndarray:
    """图片预处理：放大过小的图 + 灰度 + CLAHE 对比度增强。

    CLAHE 能把手写铅笔等淡色笔迹拉深、弱化阴影，对潦草字识别帮助最大。
    """
    import cv2

    data = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片")

    height, width = img.shape[:2]
    if max(height, width) < 1200:
        scale = 1600 / max(height, width)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def recognize(image_bytes: bytes) -> str:
    """把图片字节识别成文字，按阅读顺序（自上而下、自左而右）拼接。

    识别失败或未识别到文字时返回空字符串。
    """
    engine = _get_engine()
    if engine is None:
        return ""

    try:
        image = _preprocess(image_bytes)
        result, _elapse = engine(image)
    except Exception:
        return ""

    if not result:
        return ""

    # 每个框：顶边 y、左边 x、高度、文字
    boxes: list[dict] = []
    for box, text, _score in result:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        text = (text or "").strip()
        if not text:
            continue
        boxes.append(
            {
                "top": min(ys),
                "left": min(xs),
                "height": max(ys) - min(ys),
                "text": text,
            }
        )
    if not boxes:
        return ""

    # 按平均文字高度的一半作为「同一行」的容差，把同一行内的框拼成一个段落
    avg_height = sum(b["height"] for b in boxes) / len(boxes)
    tolerance = max(8, avg_height * 0.5)

    boxes.sort(key=lambda b: (b["top"], b["left"]))
    lines: list[dict] = []
    for b in boxes:
        if lines and abs(b["top"] - lines[-1]["top"]) <= tolerance:
            lines[-1]["parts"].append(b["text"])
            lines[-1]["top"] = min(lines[-1]["top"], b["top"])
        else:
            lines.append({"top": b["top"], "parts": [b["text"]]})

    return "\n".join(" ".join(line["parts"]) for line in lines)
