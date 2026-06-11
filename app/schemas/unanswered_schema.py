from datetime import datetime

from pydantic import BaseModel, Field


class UnansweredDetail(BaseModel):
    id: int
    question: str
    normalized_question: str
    summary: str
    system_name: str
    module_name: str
    tags: str
    frequency: int
    status: str
    question_log_id: int | None
    convert_card_id: int | None
    last_seen_time: datetime | None
    create_time: datetime
    update_time: datetime | None = None


class UnansweredDraftPreview(BaseModel):
    title: str
    question: str
    answer: str
    troubleshooting_steps: str = ""
    solution: str = ""
    risk_notice: str = ""
    system_name: str = ""
    module_name: str = ""
    tags: str = ""
    provider: str = "template"
    degraded: bool = False


class UnansweredConvertRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    system_name: str | None = None
    module_name: str | None = None
    tags: str | None = None
    scene: str | None = None
    reason_analysis: str | None = None
    troubleshooting_steps: str | None = None
    solution: str | None = None
    risk_notice: str | None = None
    source_group: str | None = "未命中沉淀"
    source_user: str | None = "admin"


class UnansweredConvertResult(BaseModel):
    unanswered_id: int
    convert_card_id: int
    knowledge_card_id: int
    status: str = "converted"


class UnansweredListResponse(BaseModel):
    items: list[UnansweredDetail]
    total: int
    page: int
    page_size: int
