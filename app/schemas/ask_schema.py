"""问答 API 请求/响应模型（/api/ask）。"""

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    """POST /api/ask 请求体。"""

    question: str = Field(description="用户问题文本")
    user_id: str | None = Field(default=None, description="用户标识，默认 anonymous")
    group_id: str | None = Field(default=None, description="群组标识，默认 demo_group")
    source_type: str = Field(default="web", description="来源类型：web / wecom 等")


class AskSourceItem(BaseModel):
    """命中知识卡片来源项。"""

    card_id: int = Field(description="知识卡片 ID")
    title: str = Field(description="知识卡片标题")
    score: float = Field(description="向量相似度分数")


class AskResponse(BaseModel):
    """POST /api/ask 响应体（结构已冻结）。"""

    matched: bool = Field(description="是否命中知识库")
    answer: str = Field(description="回答正文")
    sources: list[AskSourceItem] = Field(default_factory=list, description="命中来源列表")
    similarity_score: float = Field(description="最高相似度分数")
    question_log_id: int | None = Field(default=None, description="提问日志 ID，空问题为 null")
    fallback_reason: str | None = Field(default=None, description="未命中或异常原因")
    need_human: bool = Field(default=False, description="是否建议人工处理")
    risk_level: str = Field(default="low", description="风险等级")
    confidence_level: str | None = Field(default=None, description="置信度等级：high/medium/low/none")
    answer_status: str | None = Field(default=None, description="回答状态")
    answer_source: str | None = Field(default=None, description="回答来源")
