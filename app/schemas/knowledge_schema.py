from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AuditStatusInput = Literal["approved", "rejected"]


class KnowledgeFormBase(BaseModel):
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
    source_group: str | None = None
    source_user: str | None = None


class KnowledgeCreate(KnowledgeFormBase):
    pass


class KnowledgeUpdate(KnowledgeFormBase):
    pass


class KnowledgeAuditRequest(BaseModel):
    audit_status: AuditStatusInput
    audit_user: str = "admin"
    audit_remark: str | None = None

    @field_validator("audit_remark")
    @classmethod
    def validate_reject_remark(cls, value: str | None, info) -> str | None:
        audit_status = info.data.get("audit_status")
        if audit_status == "rejected" and not (value and value.strip()):
            raise ValueError("审核拒绝时必须填写审核备注")
        return value


class KnowledgeDetail(BaseModel):
    id: int
    title: str
    question: str | None
    answer: str | None
    system_name: str | None
    module_name: str | None
    tags: str | None
    scene: str | None
    reason_analysis: str | None
    troubleshooting_steps: str | None
    solution: str | None
    risk_notice: str | None
    source_group: str | None
    source_user: str | None
    audit_status: str
    audit_user: str | None
    audit_time: datetime | None
    audit_remark: str | None
    vector_status: str
    vector_id: str | None
    vector_error: str | None
    content_hash: str | None
    version: int
    enabled: int
    deleted: int
    create_user: str | None
    update_user: str | None
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}
