"""用户反馈相关请求/响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackType = Literal["useful", "useless", "supplement", "need_human"]

VALID_FEEDBACK_TYPES = {"useful", "useless", "supplement", "need_human"}


class FeedbackSubmitRequest(BaseModel):
    """统一反馈提交请求体（阶段4增强）。"""

    user_id: str = Field(default="anonymous", description="反馈用户标识")
    group_id: str | None = Field(default=None, description="来源群 ID")
    feedback_type: Literal["useful", "useless", "supplement"] = Field(..., description="反馈类型")
    reason_type: str | None = Field(default=None, description="无用原因类型")
    reason_text: str | None = Field(default=None, description="无用原因说明")
    supplement_text: str | None = Field(default=None, description="补充/纠错内容")
    question_log_id: int | None = Field(default=None, gt=0, description="可选：指定绑定的问答日志 ID")
    comment: str | None = Field(default=None, max_length=500, description="兼容旧版备注字段")

    @field_validator("reason_text", "supplement_text", "comment")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class FeedbackCreateRequest(BaseModel):
    """提交反馈请求体（兼容旧版页面）。"""

    question_log_id: int = Field(..., gt=0, description="关联的问答日志 ID")
    feedback_type: Literal["useful", "useless", "need_human"] = Field(..., description="反馈类型")
    user_id: str | None = Field(default="anonymous", description="反馈用户标识")
    comment: str | None = Field(default=None, max_length=500, description="补充说明")

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class FeedbackDetail(BaseModel):
    """反馈详情（列表/详情展示）。"""

    id: int = Field(..., description="反馈记录 ID")
    question_log_id: int | None = Field(..., description="问答日志 ID")
    feedback_type: str = Field(..., description="反馈类型")
    user_id: str = Field(..., description="用户标识")
    comment: str = Field(default="", description="补充说明")
    knowledge_card_id: int | None = Field(default=None, description="关联知识卡片 ID")
    reason_type: str | None = Field(default=None, description="无用原因类型")
    reason_text: str | None = Field(default=None, description="无用原因")
    supplement_text: str | None = Field(default=None, description="补充内容")
    status: str = Field(default="new", description="处理状态")
    create_time: datetime = Field(..., description="创建时间")
    question_summary: str = Field(default="", description="关联问题摘要")
