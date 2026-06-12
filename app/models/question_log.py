"""提问日志 ORM 模型（表 question_log）。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class QuestionLog(Base):
    """每次有效提问的完整记录（Web / 企微共用）。"""

    __tablename__ = "question_log"
    __table_args__ = (
        Index("idx_question_request_id", "request_id"),
        Index("idx_question_create_time", "create_time"),
        Index("idx_question_matched", "matched"),
        Index("idx_question_user_id", "user_id"),
        Index("idx_question_group_id", "group_id"),
        Index("idx_question_source_type", "source_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    request_id: Mapped[str | None] = mapped_column(String(64))  # 请求 UUID
    question_raw: Mapped[str | None] = mapped_column(Text)  # 原始问题
    question_masked: Mapped[str | None] = mapped_column(Text)  # 脱敏问题
    rewritten_question: Mapped[str | None] = mapped_column(Text)  # 改写问题
    user_id: Mapped[str | None] = mapped_column(String(100))  # 用户 ID
    group_id: Mapped[str | None] = mapped_column(String(100))  # 群组 ID
    source_type: Mapped[str | None] = mapped_column(String(50))  # 来源 web/wecom
    intent: Mapped[str | None] = mapped_column(String(50))  # 意图
    matched: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 是否命中 0/1
    matched_card_ids: Mapped[str | None] = mapped_column(String(500))  # 命中卡片 ID 列表
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))  # 相似度
    answer: Mapped[str | None] = mapped_column(Text)  # 回答正文
    fallback_reason: Mapped[str | None] = mapped_column(String(500))  # 未命中/降级原因
    need_human: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 需人工 0/1
    risk_level: Mapped[str | None] = mapped_column(String(20))  # 风险等级
    error_stage: Mapped[str | None] = mapped_column(String(100))  # LLM 出错阶段
    error_message: Mapped[str | None] = mapped_column(Text)  # LLM 出错信息
    latency_ms: Mapped[int | None] = mapped_column(Integer)  # 总耗时 ms
    retrieval_time_ms: Mapped[int | None] = mapped_column(Integer)  # 检索耗时 ms
    answer_time_ms: Mapped[int | None] = mapped_column(Integer)  # 生成耗时 ms
    llm_tokens: Mapped[int | None] = mapped_column(Integer)  # LLM token
    langsmith_trace_id: Mapped[str | None] = mapped_column(String(200))  # LangSmith trace ID
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
