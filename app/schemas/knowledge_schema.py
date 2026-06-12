"""知识卡片相关请求/响应模型。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AuditStatusInput = Literal["approved", "rejected"]  # 审核结果：通过 / 拒绝


class KnowledgeFormBase(BaseModel):
    """知识卡片表单公共字段（创建/更新共用）。"""

    title: str = Field(..., min_length=1, max_length=200, description="卡片标题")
    question: str = Field(..., min_length=1, description="标准问题")
    answer: str = Field(..., min_length=1, description="标准答案")
    system_name: str | None = Field(default=None, description="所属系统")
    module_name: str | None = Field(default=None, description="所属模块")
    tags: str | None = Field(default=None, description="标签，逗号分隔")
    scene: str | None = Field(default=None, description="适用场景")
    reason_analysis: str | None = Field(default=None, description="原因分析")
    troubleshooting_steps: str | None = Field(default=None, description="排查步骤")
    solution: str | None = Field(default=None, description="解决方案")
    risk_notice: str | None = Field(default=None, description="风险提醒")
    source_group: str | None = Field(default=None, description="来源实施群")
    source_user: str | None = Field(default=None, description="来源用户")


class KnowledgeCreate(KnowledgeFormBase):
    """创建知识卡片请求体。"""

    pass


class KnowledgeUpdate(KnowledgeFormBase):
    """更新知识卡片请求体。"""

    pass


class KnowledgeAuditRequest(BaseModel):
    """知识卡片审核请求体。"""

    audit_status: AuditStatusInput = Field(..., description="审核结果")
    audit_user: str = Field(default="admin", description="审核人")
    audit_remark: str | None = Field(default=None, description="审核备注（拒绝时必填）")

    @field_validator("audit_remark")
    @classmethod
    def validate_reject_remark(cls, value: str | None, info) -> str | None:
        """拒绝审核时必须填写备注。"""
        audit_status = info.data.get("audit_status")
        if audit_status == "rejected" and not (value and value.strip()):
            raise ValueError("审核拒绝时必须填写审核备注")
        return value


class KnowledgeDetail(BaseModel):
    """知识卡片完整详情（含审核与向量状态）。"""

    id: int = Field(..., description="卡片 ID")
    title: str = Field(..., description="标题")
    question: str | None = Field(default=None, description="标准问题")
    answer: str | None = Field(default=None, description="标准答案")
    system_name: str | None = Field(default=None, description="所属系统")
    module_name: str | None = Field(default=None, description="所属模块")
    tags: str | None = Field(default=None, description="标签")
    scene: str | None = Field(default=None, description="适用场景")
    reason_analysis: str | None = Field(default=None, description="原因分析")
    troubleshooting_steps: str | None = Field(default=None, description="排查步骤")
    solution: str | None = Field(default=None, description="解决方案")
    risk_notice: str | None = Field(default=None, description="风险提醒")
    source_group: str | None = Field(default=None, description="来源群")
    source_user: str | None = Field(default=None, description="来源用户")
    audit_status: str = Field(..., description="审核状态")
    audit_user: str | None = Field(default=None, description="审核人")
    audit_time: datetime | None = Field(default=None, description="审核时间")
    audit_remark: str | None = Field(default=None, description="审核备注")
    vector_status: str = Field(..., description="向量同步状态")
    vector_id: str | None = Field(default=None, description="Qdrant 向量点 ID")
    vector_error: str | None = Field(default=None, description="向量同步错误信息")
    content_hash: str | None = Field(default=None, description="内容哈希")
    version: int = Field(..., description="版本号")
    enabled: int = Field(..., description="是否启用：1 启用 / 0 停用")
    deleted: int = Field(..., description="软删除标记")
    create_user: str | None = Field(default=None, description="创建人")
    update_user: str | None = Field(default=None, description="更新人")
    create_time: datetime = Field(..., description="创建时间")
    update_time: datetime = Field(..., description="更新时间")

    model_config = {"from_attributes": True}
