"""请求/响应模型。

只定义请求体——响应直接返回 core/ 产出的字典。原因是 core/ 的返回结构就是网页版
正在用的那份，额外套一层 Pydantic 模型等于把同一份结构维护两遍，改一处漏一处的
风险比类型检查带来的收益大。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 认证
# --------------------------------------------------------------------------- #
class SendCodeRequest(BaseModel):
    email: str = Field(..., max_length=120, description="接收验证码的邮箱")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=20, description="英文名，仅大小写字母")
    chinese_name: str = Field(..., min_length=1, max_length=50, description="中文名")
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=6, max_length=64)
    confirm_password: str = Field(..., max_length=64)
    code: str = Field(..., min_length=1, max_length=10)


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., max_length=64)


class WechatLoginRequest(BaseModel):
    """微信一键登录。code 来自 wx.login，后端换 openid。"""

    code: str = Field(..., max_length=128)


# --------------------------------------------------------------------------- #
# 预习 / 复习
# --------------------------------------------------------------------------- #
class QuizGradeRequest(BaseModel):
    book: str = Field(..., max_length=50)
    unit: str = Field(..., max_length=100)
    quiz_type: str = Field(..., pattern="^(preview|review)$")
    # {"0": "选项文本", ...}，键是题目下标（字符串），值是所选选项原文
    answers: dict[str, str]


class StudyPlanRequest(BaseModel):
    plan_type: str = Field(..., pattern="^(preview|review)$")
    book: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=100)


# --------------------------------------------------------------------------- #
# 作业
# --------------------------------------------------------------------------- #
class HomeworkGradeRequest(BaseModel):
    text: str = Field(..., min_length=10, description="作业原文（图片识别后回填或手动输入）")
    book: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=100)


class RecognizeRequest(BaseModel):
    """作业图片上传参数（放在 query，图片走 multipart body）。"""

    book: str | None = Field(default=None, max_length=50)
    unit: str | None = Field(default=None, max_length=100)


# --------------------------------------------------------------------------- #
# 模拟试卷
# --------------------------------------------------------------------------- #
class MockExamGradeRequest(BaseModel):
    book: str = Field(..., max_length=50)
    answers: dict[str, str] = Field(default_factory=dict, description="客观题：题号 → 所选答案")
    writings: dict[str, str] = Field(default_factory=dict, description="写作板块作答")


# --------------------------------------------------------------------------- #
# 会员
# --------------------------------------------------------------------------- #
class PurchaseRequest(BaseModel):
    plan: str = Field(..., max_length=20, description="月卡 / 季卡 / 年卡")


# --------------------------------------------------------------------------- #
# 客服留言
# --------------------------------------------------------------------------- #
class MessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class ReplyRequest(BaseModel):
    reply: str = Field(..., min_length=1, max_length=2000)
