from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str
    user_id: str | None = None
    group_id: str | None = None
    source_type: str = "web"


class AskSourceItem(BaseModel):
    card_id: int
    title: str
    score: float


class AskResponse(BaseModel):
    matched: bool
    answer: str
    sources: list[AskSourceItem] = Field(default_factory=list)
    similarity_score: float
    question_log_id: int | None = None
    fallback_reason: str | None = None
    need_human: bool = False
    risk_level: str = "low"
