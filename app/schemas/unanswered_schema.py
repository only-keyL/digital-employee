"""未命中问题相关请求/响应模型。"""

from datetime import datetime

from pydantic import BaseModel, Field


class UnansweredDetail(BaseModel):
    """未命中问题详情。"""

    id: int = Field(..., description="未命中记录 ID")
    question: str = Field(..., description="原始问题")
    normalized_question: str = Field(..., description="归一化后的问题")
    summary: str = Field(..., description="问题摘要")
    system_name: str = Field(..., description="推断所属系统")
    module_name: str = Field(..., description="推断所属模块")
    tags: str = Field(..., description="标签")
    frequency: int = Field(..., description="出现频次")
    status: str = Field(..., description="处理状态：pending / converted / ignored")
    question_log_id: int | None = Field(default=None, description="最近关联问答日志 ID")
    convert_card_id: int | None = Field(default=None, description="转化后的知识卡片 ID")
    last_seen_time: datetime | None = Field(default=None, description="最近出现时间")
    create_time: datetime = Field(..., description="创建时间")
    update_time: datetime | None = Field(default=None, description="更新时间")


class UnansweredDraftPreview(BaseModel):
    """LLM/模板生成的知识卡片草稿预览。"""

    title: str = Field(..., description="卡片标题")
    question: str = Field(..., description="标准问题")
    answer: str = Field(..., description="标准答案")
    troubleshooting_steps: str = Field(default="", description="排查步骤")
    solution: str = Field(default="", description="处理建议")
    risk_notice: str = Field(default="", description="风险提醒")
    system_name: str = Field(default="", description="所属系统")
    module_name: str = Field(default="", description="所属模块")
    tags: str = Field(default="", description="标签")
    provider: str = Field(default="template", description="草稿生成来源：template / llm")
    degraded: bool = Field(default=False, description="是否降级为模板生成")


class UnansweredConvertRequest(BaseModel):
    """将未命中问题转为知识卡片的请求体（可编辑草稿字段）。"""

    title: str = Field(..., min_length=1, max_length=200, description="卡片标题")
    question: str = Field(..., min_length=1, description="标准问题")
    answer: str = Field(..., min_length=1, description="标准答案")
    system_name: str | None = Field(default=None, description="所属系统")
    module_name: str | None = Field(default=None, description="所属模块")
    tags: str | None = Field(default=None, description="标签")
    scene: str | None = Field(default=None, description="适用场景")
    reason_analysis: str | None = Field(default=None, description="原因分析")
    troubleshooting_steps: str | None = Field(default=None, description="排查步骤")
    solution: str | None = Field(default=None, description="解决方案")
    risk_notice: str | None = Field(default=None, description="风险提醒")
    source_group: str | None = Field(default="未命中沉淀", description="来源群")
    source_user: str | None = Field(default="admin", description="来源用户")


class UnansweredConvertResult(BaseModel):
    """未命中转知识卡片的结果。"""

    unanswered_id: int = Field(..., description="未命中记录 ID")
    convert_card_id: int = Field(..., description="新建知识卡片 ID")
    knowledge_card_id: int = Field(..., description="知识卡片 ID（同 convert_card_id）")
    status: str = Field(default="converted", description="转化后状态")


class UnansweredListResponse(BaseModel):
    """未命中问题分页列表。"""

    items: list[UnansweredDetail] = Field(..., description="当前页数据")
    total: int = Field(..., description="总条数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
