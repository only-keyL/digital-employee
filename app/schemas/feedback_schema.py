from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

FeedbackType = Literal["useful", "useless", "need_human"]

VALID_FEEDBACK_TYPES = {"useful", "useless", "need_human"}


class FeedbackCreateRequest(BaseModel):
    question_log_id: int = Field(..., gt=0)
    feedback_type: FeedbackType
    user_id: str | None = "anonymous"
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class FeedbackDetail(BaseModel):
    id: int
    question_log_id: int
    feedback_type: str
    user_id: str
    comment: str
    create_time: datetime
    question_summary: str = ""
