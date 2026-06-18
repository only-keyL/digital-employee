"""上下文增强与会话缓存 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationContext(BaseModel):
    """Redis 中保存的最近一轮问答摘要。"""

    last_question: str = Field(description="上一轮用户原始问题")
    last_rewritten_question: str | None = Field(default=None, description="上一轮改写后问题")
    last_answer_summary: str | None = Field(default=None, description="上一轮回答摘要，最长 300 字")
    system_name: str | None = Field(default=None, description="上一轮归属系统")
    module_name: str | None = Field(default=None, description="上一轮归属模块")
    primary_matched_card_id: int | None = Field(default=None, description="上一轮 top1 知识卡片 ID")
    primary_matched_card_title: str | None = Field(default=None, description="上一轮 top1 知识卡片标题")
    confidence_level: str | None = Field(default=None, description="上一轮置信度等级")
    updated_at: str | None = Field(default=None, description="上下文更新时间 ISO 格式")


class ContextEnhanceResult(BaseModel):
    """上下文增强结果。"""

    original_question: str = Field(description="用户原始问题")
    rewritten_question: str = Field(description="改写后用于检索的问题")
    used_context: bool = Field(default=False, description="是否使用了上下文增强")
    context_source: str | None = Field(
        default=None,
        description="上下文来源：redis_recent_turn / user_recent_modules / none",
    )
    context_summary: str | None = Field(default=None, description="上下文摘要说明，便于日志排查")
