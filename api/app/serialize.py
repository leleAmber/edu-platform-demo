"""响应序列化：把 core/ 的用户字典转成给客户端的形状。

绝不直接返回 database 的用户行——里面有 password 哈希。
"""

from __future__ import annotations

import copy

from core import vip  # noqa: E402


# --------------------------------------------------------------------------- #
# 题目脱敏
# --------------------------------------------------------------------------- #
# core 的题目结构里带 answer / explain：网页版全在服务端渲染，不出去无所谓；
# 走 HTTP 就不同了——直接把带答案的题目发给客户端，等于把答案随卷子一起发出去，
# 抓个包就能满分。所以题目一律先脱敏再下发，答案只留在服务端供批改使用。
#
# 批改不受影响：grade_quiz / grade_mock_exam 都自己回 _session_store() 取那份
# 带答案的原始缓存，不依赖客户端回传的内容。
_ANSWER_KEYS = ("answer", "explain")


def _strip_question(question: dict) -> dict:
    return {key: value for key, value in question.items() if key not in _ANSWER_KEYS}


def public_questions(questions: list[dict] | None) -> list[dict]:
    """去掉答案与解析的练习题列表。"""
    return [_strip_question(q) for q in (questions or [])]


def public_unit_content(content: dict) -> dict:
    """预习/复习单元内容：练习脱敏，词汇与句型原样保留。"""
    payload = copy.deepcopy(content)
    for key in ("preview_quiz", "review_quiz"):
        if key in payload:
            payload[key] = public_questions(payload.get(key))
    return payload


def public_exam(exam: dict) -> dict:
    """模拟试卷：所有题型的客观题都去掉答案与解析，保留题面与选项。"""
    payload = copy.deepcopy(exam)
    for section in payload.get("sections", []):
        if section.get("passages"):
            for passage in section["passages"]:
                passage["questions"] = public_questions(passage.get("questions"))
        if section.get("questions"):
            section["questions"] = public_questions(section["questions"])
    return payload


def user_payload(user: dict) -> dict:
    """客户端可见的用户信息（不含密码哈希）。"""
    if not user:
        return {}
    is_member = vip.is_vip(user)
    return {
        "username": user.get("username", ""),
        "chinese_name": user.get("chinese_name") or "",
        "email": user.get("email", ""),
        "role": user.get("role", "student"),
        "is_vip": is_member,
        "vip_plan": user.get("vip_plan"),
        "vip_until": user.get("vip_until"),
        "vip_until_text": vip.vip_until_text(user),
        # 是否用微信登录（决定客户端要不要显示「绑定账号」入口）
        "has_wechat": bool(user.get("openid")),
    }


def strip_homework_details(result: dict, *, is_vip: bool) -> dict:
    """按会员状态裁剪作业批改结果。

    免费用户只能看总分与对错统计，逐题解析/评语/错误类型分布是 VIP 权益。
    网页版靠页面分支（if not is_vip）来藏，API 版必须在服务端剥掉——
    否则客户端拿到完整 response 就白嫖了。
    """
    payload = {
        "mode": result.get("mode"),
        "total_score": result.get("total_score", 0),
        "right_count": result.get("right_count", 0),
        "wrong_count": result.get("wrong_count", 0),
        "question_count": result.get("question_count", 0),
        "source": result.get("source", ""),
        "note": result.get("note", ""),
        "locked": not is_vip,
    }
    if is_vip:
        payload["comment"] = result.get("comment", "")
        payload["details"] = result.get("details", [])
        payload["error_types"] = result.get("error_types", {})
    else:
        # 明确置空而不是省略键，客户端不必区分「没有」和「无权限」
        payload["comment"] = ""
        payload["details"] = []
        payload["error_types"] = {}
    return payload
