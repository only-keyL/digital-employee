"""知识卡片重复检测 API 模型。"""

from pydantic import BaseModel, Field


class DuplicateCheckItem(BaseModel):
    """单条相似知识检测结果。"""

    candidate_card_id: int | None = Field(default=None, description="候选知识卡片 ID")
    candidate_title: str | None = Field(default=None, description="候选卡片标题")
    system_name: str | None = Field(default=None, description="所属系统")
    module_name: str | None = Field(default=None, description="所属模块")
    audit_status: str | None = Field(default=None, description="候选卡片审核状态")
    similarity_score: float | None = Field(default=None, description="相似度分数")
    check_level: str = Field(description="重复等级")
    check_level_name: str = Field(description="重复等级中文名")
    suggestion: str = Field(description="处理建议")


class DuplicateCheckResult(BaseModel):
    """知识卡片重复检测结果。"""

    source_card_id: int = Field(description="被检测知识卡片 ID")
    source_title: str = Field(description="被检测知识卡片标题")
    highest_score: float | None = Field(default=None, description="最高相似度")
    highest_level: str = Field(description="最高重复等级")
    highest_level_name: str = Field(description="最高重复等级中文名")
    has_high_risk_duplicate: bool = Field(description="是否存在高度重复风险")
    items: list[DuplicateCheckItem] = Field(default_factory=list, description="相似候选列表")
    message: str = Field(description="检测结论提示")
