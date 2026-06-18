"""AskGraphV2 API 请求/响应模型。"""

from pydantic import BaseModel, Field


class AskV2Request(BaseModel):
    question: str = Field(description="用户问题")
    user_id: str | None = Field(default="anonymous")
    source: str = Field(default="api_ask_v2")


class AskV2RetrievalItem(BaseModel):
    knowledge_id: int
    title: str
    score: float
    rank: int


class AskV2Response(BaseModel):
    run_id: str
    status: str
    confidence_level: str
    top_score: float | None = None
    answer: str
    retrieval: list[AskV2RetrievalItem] = Field(default_factory=list)
    fallback_reason: str | None = None
