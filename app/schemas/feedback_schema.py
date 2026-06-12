"""用户反馈相关请求/响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackType = Literal["useful", "useless", "need_human"]  # 反馈类型：有用 / 无用 / 需人工

VALID_FEEDBACK_TYPES = {"useful", "useless", "need_human"}


class FeedbackCreateRequest(BaseModel):
    """提交反馈请求体。"""

    question_log_id: int = Field(..., gt=0, description="关联的问答日志 ID")
    feedback_type: FeedbackType = Field(..., description="反馈类型")
    user_id: str | None = Field(default="anonymous", description="反馈用户标识")
    comment: str | None = Field(default=None, max_length=500, description="补充说明")

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        """去除空白，空字符串视为 None。"""
        if value is None:
            return None
        text = value.strip()
        return text or None


class FeedbackDetail(BaseModel):
    """反馈详情（列表/详情展示）。"""

    id: int = Field(..., description="反馈记录 ID")
    question_log_id: int = Field(..., description="问答日志 ID")
    feedback_type: str = Field(..., description="反馈类型")
    user_id: str = Field(..., description="用户标识")
    comment: str = Field(..., description="补充说明")
    create_time: datetime = Field(..., description="创建时间")
    question_summary: str = Field(default="", description="关联问题摘要")
