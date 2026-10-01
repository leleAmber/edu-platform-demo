"""大模型批改层：通过 OpenAI 兼容接口调用国产大模型（智谱 GLM / DeepSeek / Qwen 等）。

配置从 .streamlit/secrets.toml 读取：
- 单个 key：LLM_API_KEY；
- 多 key 分流：LLM_API_KEYS = ["key1", "key2", ...]（填写后优先于 LLM_API_KEY）。
未配置任何 key 时 is_available() 返回 False，上层自动退回本地规则引擎。
每次请求按轮询顺序尝试各 key，遇到限流/失败自动换下一个，全部失败才返回 None。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import re
from collections import OrderedDict

import requests
import streamlit as st

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-4-flash"
DEFAULT_VISION_MODEL = "glm-4v-flash"

_GRADING_SYSTEM = (
    "你是一位经验丰富的高三英语辅导老师。用户会发来一份高中英语作业（可能是作文、选择题或填空题），"
    "请判断对错并批改。严格只输出一个 JSON 对象，不要输出任何其他文字、注释或代码块标记。\n"
    'JSON 结构（键名固定，不要改动）：\n'
    '{"total_score": 0到100的整数, "comment": "一句话总评", "details": [{"index": 1, '
    '"question": "题目或原句", "your_answer": "学生作答（作文可留空字符串）", '
    '"correct_answer": "正确答案或修改后的句子", "is_right": true或false, '
    '"error_type": "错误类型，正确则为空字符串", "explain": "简明解析"}]}\n'
    "规则：\n"
    "- 作文：按句子拆分成多个 details 项，正确的句子 is_right=true，有问题的 is_right=false 并给出修改与解析；\n"
    "- 选择题/填空题：每个小题一条 details，判断对错并给出正确答案与解析；\n"
    "- total_score 根据错误多少给出合理分数。"
)

_TYPE_HINT = {
    "writing": "这是一篇英语作文，请从语法、用词、连贯性角度逐句批改并给分。",
    "choice": "这是选择题，请判断学生选的对错，并给出正确答案与解析。",
    "blank": "这是填空题，请判断学生填的对错，并给出正确答案与解析。",
    "reading": "这是一篇阅读理解（含文章和题目）。请只批改题目：结合文章内容判断学生每道题作答对错，"
    "并给出正确答案与解析，文章本身不需要批改。",
}

_request_counter = itertools.count()

# --------------------------------------------------------------------------- #
# 结果缓存：同一份作业 / 同一张图不重复消耗 API 额度，进程内 LRU 淘汰
# --------------------------------------------------------------------------- #
_CACHE_MAX = 512
_result_cache: "OrderedDict[str, dict | str]" = OrderedDict()


def _cache_key(prefix: str, *parts) -> str:
    """生成稳定缓存键：对每个 part 做 SHA-1 摘要。"""
    digest = hashlib.sha1()
    for part in parts:
        digest.update(part if isinstance(part, bytes) else str(part).encode("utf-8"))
    return f"{prefix}:{digest.hexdigest()}"


def _cache_get(key: str):
    """读缓存并刷新 LRU 位置；未命中返回 None。"""
    value = _result_cache.get(key)
    if value is not None:
        _result_cache.move_to_end(key)
    return value


def _cache_put(key: str, value) -> None:
    """写缓存，超出上限时按 LRU 淘汰最久未用的条目。"""
    _result_cache[key] = value
    _result_cache.move_to_end(key)
    while len(_result_cache) > _CACHE_MAX:
        _result_cache.popitem(last=False)


def _providers() -> list[dict]:
    """读取所有可用的模型配置，未配置任何 key 时返回空列表。"""
    try:
        base_url = str(st.secrets.get("LLM_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL).strip().rstrip("/")
        model = str(st.secrets.get("LLM_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL).strip()
        vision_model = str(st.secrets.get("LLM_VISION_MODEL", DEFAULT_VISION_MODEL) or DEFAULT_VISION_MODEL).strip()

        keys = st.secrets.get("LLM_API_KEYS")
        if keys:
            api_keys = [str(k).strip() for k in keys if str(k).strip()]
        else:
            single = str(st.secrets.get("LLM_API_KEY", "") or "").strip()
            api_keys = [single] if single else []
    except Exception:
        return []

    return [
        {"base_url": base_url, "api_key": k, "model": model, "vision_model": vision_model}
        for k in api_keys
    ]


def is_available() -> bool:
    """大模型批改是否已配置。"""
    return bool(_providers())


def _chat_once(provider: dict, payload: dict) -> str | None:
    """对单个 provider 发一次请求，成功返回文本内容，失败/限流返回 None。"""
    headers = {
        "Authorization": f"Bearer {provider['api_key']}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            f"{provider['base_url']}/chat/completions",
            json=payload,
            headers=headers,
            timeout=60,
        )
    except Exception:
        return None
    if resp.status_code != 200:
        return None  # 含 429 限流 / 401 无效 key 等，交给上层换下一个
    try:
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return None
    if not isinstance(content, str):
        return None
    return content


def _chat(payload: dict, model_key: str = "model") -> str | None:
    """按轮询顺序尝试各 provider，失败自动换下一个 key，全部失败返回 None。"""
    providers = _providers()
    if not providers:
        return None
    start = next(_request_counter) % len(providers)
    for offset in range(len(providers)):
        provider = providers[(start + offset) % len(providers)]
        req = {**payload, "model": provider.get(model_key) or payload.get("model")}
        content = _chat_once(provider, req)
        if content is not None:
            return content
    return None


def _parse_json(text: str) -> dict | None:
    """从模型输出里提取 JSON，容忍代码块包裹与多余文字。"""
    if not text:
        return None
    text = text.strip()

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _normalize(parsed: dict) -> dict:
    """把模型返回的 JSON 规范化成统一结构。"""
    raw_details = parsed.get("details") or []
    details = []
    for i, item in enumerate(raw_details, 1):
        if not isinstance(item, dict):
            continue
        details.append(
            {
                "index": item.get("index", i),
                "question": str(item.get("question", "") or ""),
                "your_answer": str(item.get("your_answer", "") or ""),
                "correct_answer": str(item.get("correct_answer", "") or ""),
                "is_right": item.get("is_right") is True,
                "error_type": str(item.get("error_type", "") or ""),
                "explain": str(item.get("explain", "") or ""),
            }
        )

    total_score = parsed.get("total_score")
    if not isinstance(total_score, (int, float)):
        total_score = 0
    total_score = max(0, min(100, int(total_score)))

    return {
        "total_score": total_score,
        "comment": str(parsed.get("comment", "") or ""),
        "details": details,
    }


def grade_homework(text: str, question_type: str) -> dict | None:
    """调用大模型批改作业，返回 {"total_score", "comment", "details"}，失败/未配置返回 None。

    相同（模型 + 题型 + 内容）的请求命中缓存，不重复消耗 API 额度。
    """
    providers = _providers()
    if not providers:
        return None

    cache_key = _cache_key("grade", providers[0]["model"], question_type, text)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    type_hint = _TYPE_HINT.get(question_type, "请判断对错并给出解析。")
    payload = {
        "model": providers[0]["model"],
        "messages": [
            {"role": "system", "content": _GRADING_SYSTEM},
            {"role": "user", "content": f"{type_hint}\n\n作业内容：\n{text}"},
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    content = _chat(payload)
    if not content:
        return None

    parsed = _parse_json(content)
    if not parsed:
        return None
    result = _normalize(parsed)
    _cache_put(cache_key, result)
    return result


_SENTENCE_SYSTEM = (
    "你是高中英语老师。判断下面这句英语是否有语法、用词或标点错误。"
    '严格只输出一个 JSON：{"is_right": true或false, "corrected": "正确或修改后的句子", '
    '"error_type": "错误类型，正确则为空字符串", "explain": "一句话解析"}'
)


def grade_sentence(sentence: str) -> dict | None:
    """批改单个句子，返回 {is_right, corrected, error_type, explain}，失败返回 None。"""
    providers = _providers()
    if not providers:
        return None

    cache_key = _cache_key("sentence", providers[0]["model"], sentence)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = {
        "model": providers[0]["model"],
        "messages": [
            {"role": "system", "content": _SENTENCE_SYSTEM},
            {"role": "user", "content": sentence},
        ],
        "temperature": 0.0,
        "max_tokens": 300,
    }
    content = _chat(payload)
    if not content:
        return None

    parsed = _parse_json(content)
    if not parsed:
        return None

    result = {
        "is_right": parsed.get("is_right") is True,
        "corrected": str(parsed.get("corrected", "") or "").strip() or sentence,
        "error_type": str(parsed.get("error_type", "") or "").strip(),
        "explain": str(parsed.get("explain", "") or "").strip(),
    }
    _cache_put(cache_key, result)
    return result


def grade_writing(sentences: list[str]) -> dict | None:
    """并行批改一组句子（跨 key 池），合并成 {total_score, comment, details}。"""
    providers = _providers()
    if not providers:
        return None
    if not sentences:
        return {"total_score": 0, "comment": "", "details": []}

    from concurrent.futures import ThreadPoolExecutor

    workers = max(1, len(providers))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(grade_sentence, sentences))

    details = []
    wrong_count = 0
    for i, (sentence, r) in enumerate(zip(sentences, results), 1):
        if r is None:
            details.append(
                {
                    "index": i,
                    "question": sentence,
                    "your_answer": "",
                    "correct_answer": "",
                    "is_right": None,
                    "error_type": "",
                    "explain": "该句暂无法自动判断，请人工核对。",
                }
            )
            continue
        if not r["is_right"]:
            wrong_count += 1
        details.append(
            {
                "index": i,
                "question": sentence,
                "your_answer": "",
                "correct_answer": r["corrected"],
                "is_right": r["is_right"],
                "error_type": r["error_type"],
                "explain": r["explain"],
            }
        )

    total_score = max(40, 100 - 8 * wrong_count)
    return {
        "total_score": total_score,
        "comment": "",
        "details": details,
    }


_OVERALL_SYSTEM = (
    "你是高中英语老师。学生写了一篇英语作文，请给出整体评价。"
    '严格只输出一个 JSON：{"total_score": 0到100的整数, '
    '"comment": "两三句话的中文总评，涵盖内容要点、结构连贯、语言表达"}'
)


def grade_writing_overall(text: str) -> dict | None:
    """给整篇作文打综合分 + 一句话总评，返回 {total_score, comment}，失败返回 None。"""
    providers = _providers()
    if not providers:
        return None

    cache_key = _cache_key("overall", providers[0]["model"], text)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = {
        "model": providers[0]["model"],
        "messages": [
            {"role": "system", "content": _OVERALL_SYSTEM},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": 300,
    }
    content = _chat(payload)
    if not content:
        return None

    parsed = _parse_json(content)
    if not parsed:
        return None

    total = parsed.get("total_score")
    if not isinstance(total, (int, float)):
        total = 0
    result = {
        "total_score": max(0, min(100, int(total))),
        "comment": str(parsed.get("comment", "") or "").strip(),
    }
    _cache_put(cache_key, result)
    return result


_VISION_PROMPT = "识别图中所有文字，原样输出，不要解释，不要添加任何额外内容。"


def _data_uri(image_bytes: bytes) -> str:
    """把图片字节编码成 data URI，按文件头识别格式。"""
    import base64

    b64 = base64.b64encode(image_bytes).decode()
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "image/png"
    elif image_bytes[:2] == b"\xff\xd8":
        mime = "image/jpeg"
    else:
        mime = "image/png"
    return f"data:{mime};base64,{b64}"


def vision_available() -> bool:
    """视觉大模型是否已配置（用于识别图片）。"""
    return any(p.get("vision_model") for p in _providers())


def recognize_image(image_bytes: bytes) -> str | None:
    """调用视觉大模型识别图片文字，失败/未配置返回 None。

    相同（视觉模型 + 图片）的请求命中缓存，不重复消耗 API 额度。
    """
    providers = _providers()
    if not providers or not providers[0].get("vision_model"):
        return None

    cache_key = _cache_key("vision", providers[0]["vision_model"], image_bytes)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = {
        "model": providers[0]["vision_model"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image_url", "image_url": {"url": _data_uri(image_bytes)}},
                ],
            }
        ],
        "temperature": 0.0,
        "max_tokens": 1000,
    }
    content = _chat(payload, model_key="vision_model")
    if not content:
        return None
    result = content.strip()
    _cache_put(cache_key, result)
    return result
