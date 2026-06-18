"""后台审核与投稿治理 API Schema（阶段 5）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ContributionListItem(BaseModel):
    """投稿列表项：不含完整 raw_content。"""

    id: int
    contribution_id: str
    source: str
    message_id: str | None = None
    group_id: str | None = None
    user_id: str
    user_name: str | None = None
    status: str
    duplicate_suspected: bool
    risk_level: str | None = None
    knowledge_card_id: int | None = None
    content_preview: str | None = Field(default=None, description="脱敏后的正文预览")
    created_at: datetime | None = None


class ContributionDetail(BaseModel):
    """投稿详情：parsed_card 字段已截断脱敏，不含完整 raw_content。"""

    id: int
    contribution_id: str
    source: str
    message_id: str | None = None
    group_id: str | None = None
    user_id: str
    user_name: str | None = None
    status: str
    content_preview: str | None = None
    parsed_card: dict[str, Any] | None = None
    missing_fields: list[str] = Field(default_factory=list)
    duplicate_result: dict[str, Any] | None = None
    risk_result: dict[str, Any] | None = None
    knowledge_card_id: int | None = None
    reject_reason: str | None = None
    duplicate_suspected: bool = False
    risk_level: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PendingKnowledgeListItem(BaseModel):
    """待审核知识卡片列表项。"""

    id: int
    title: str
    system_name: str | None = None
    module_name: str | None = None
    tags: str | None = None
    source_group: str | None = None
    source_user: str | None = None
    audit_status: str
    vector_status: str | None = None
    contribution_id: str | None = None
    create_time: datetime | None = None


class PendingKnowledgeDetail(BaseModel):
    """待审核知识详情：供审核人查看完整字段。"""

    id: int
    title: str
    question: str
    answer: str
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
    audit_status: str
    vector_status: str | None = None
    enabled: int
    contribution: ContributionListItem | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class KnowledgeReviewActionRequest(BaseModel):
    """审核通过/拒绝请求。生产环境必须接鉴权，本阶段为内部 Mock 入口。"""

    action: str = Field(..., description="approve 或 reject")
    audit_user: str = Field(..., min_length=1, description="审核人，必填")
    audit_remark: str | None = Field(default=None, description="审核备注；reject 时必填")

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"approve", "reject"}:
            raise ValueError("action 仅支持 approve 或 reject")
        return normalized


class ContributionMarkReviewRequest(BaseModel):
    """重复疑似/高风险投稿的人工标记请求。"""

    action: str = Field(..., description="mark_reviewed / ignore_duplicate / keep_blocked")
    reviewer: str = Field(..., min_length=1, description="操作人")
    remark: str | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        allowed = {"mark_reviewed", "ignore_duplicate", "keep_blocked"}
        if normalized not in allowed:
            raise ValueError(f"action 仅支持：{', '.join(sorted(allowed))}")
        return normalized


class PaginatedResponse(BaseModel):
    """通用分页包装。"""

    items: list[Any]
    total: int
    page: int
    page_size: int
