"""运营看板 API 与页面视图模型。"""

from pydantic import BaseModel, Field


class QuestionMetrics(BaseModel):
    """问答运行指标。"""

    today_count: int = Field(default=0, description="今日提问数")
    total_count: int = Field(default=0, description="总提问数")
    matched_count: int = Field(default=0, description="命中数")
    miss_count: int = Field(default=0, description="未命中数")
    hit_rate: float = Field(default=0.0, description="命中率")
    avg_latency_ms: float | None = Field(default=None, description="平均响应耗时毫秒")


class ConfidenceMetrics(BaseModel):
    """置信度分布指标。"""

    high: int = Field(default=0, description="高置信度")
    medium: int = Field(default=0, description="中置信度")
    low: int = Field(default=0, description="低置信度")
    none: int = Field(default=0, description="无置信度")


class FeedbackMetrics(BaseModel):
    """用户反馈指标。"""

    useful: int = Field(default=0, description="有用反馈数")
    useless: int = Field(default=0, description="无用反馈数")
    supplement: int = Field(default=0, description="补充反馈数")
    effective_rate: float = Field(default=0.0, description="回答有效率")


class KnowledgeMetrics(BaseModel):
    """知识库状态指标。"""

    total: int = Field(default=0, description="知识卡片总数")
    approved: int = Field(default=0, description="已审核")
    pending: int = Field(default=0, description="待审核")
    draft: int = Field(default=0, description="草稿")
    rejected: int = Field(default=0, description="已拒绝")
    enabled: int = Field(default=0, description="启用中")
    need_review: int = Field(default=0, description="待复核")


class DuplicateMetrics(BaseModel):
    """重复检测治理指标。"""

    total: int = Field(default=0, description="重复检测总次数")
    high_duplicate: int = Field(default=0, description="高度重复预警")
    suspected_duplicate: int = Field(default=0, description="疑似重复预警")
    related: int = Field(default=0, description="相关知识")
    none: int = Field(default=0, description="无明显重复")


class OperationDashboardSummary(BaseModel):
    """运营看板总览数据。"""

    question: QuestionMetrics = Field(default_factory=QuestionMetrics)
    confidence: ConfidenceMetrics = Field(default_factory=ConfidenceMetrics)
    feedback: FeedbackMetrics = Field(default_factory=FeedbackMetrics)
    knowledge: KnowledgeMetrics = Field(default_factory=KnowledgeMetrics)
    duplicate: DuplicateMetrics = Field(default_factory=DuplicateMetrics)


class TopUnansweredItem(BaseModel):
    """高频未命中问题条目。"""

    id: int = 0
    question: str = ""
    frequency: int = 0
    status: str = ""
    last_seen_time: str | None = None


class TopModuleItem(BaseModel):
    """高频系统/模块条目。"""

    system_name: str = ""
    module_name: str = ""
    ask_count: int = 0


class TopReferencedCardItem(BaseModel):
    """最常被引用知识卡片条目。"""

    card_id: int = 0
    title: str = ""
    reference_count: int = 0
    last_reference_time: str | None = None


class RiskCardItem(BaseModel):
    """风险知识卡片条目。"""

    card_id: int = 0
    title: str = ""
    system_name: str | None = None
    module_name: str | None = None
    useful_count: int = 0
    useless_count: int = 0
    supplement_count: int = 0
    quality_score: float | None = None
    need_review: int = 0


class OperationDashboardTops(BaseModel):
    """运营看板 Top 列表数据。"""

    top_unanswered: list[TopUnansweredItem] = Field(default_factory=list)
    top_modules: list[TopModuleItem] = Field(default_factory=list)
    top_referenced_cards: list[TopReferencedCardItem] = Field(default_factory=list)
    risk_cards: list[RiskCardItem] = Field(default_factory=list)
