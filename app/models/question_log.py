from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class QuestionLog(Base):
    __tablename__ = "question_log"
    __table_args__ = (
        Index("idx_question_request_id", "request_id"),
        Index("idx_question_create_time", "create_time"),
        Index("idx_question_matched", "matched"),
        Index("idx_question_user_id", "user_id"),
        Index("idx_question_group_id", "group_id"),
        Index("idx_question_source_type", "source_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    question_raw: Mapped[str | None] = mapped_column(Text)
    question_masked: Mapped[str | None] = mapped_column(Text)
    rewritten_question: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[str | None] = mapped_column(String(100))
    group_id: Mapped[str | None] = mapped_column(String(100))
    source_type: Mapped[str | None] = mapped_column(String(50))
    intent: Mapped[str | None] = mapped_column(String(50))
    matched: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    matched_card_ids: Mapped[str | None] = mapped_column(String(500))
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    answer: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(String(500))
    need_human: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    risk_level: Mapped[str | None] = mapped_column(String(20))
    error_stage: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    retrieval_time_ms: Mapped[int | None] = mapped_column(Integer)
    answer_time_ms: Mapped[int | None] = mapped_column(Integer)
    llm_tokens: Mapped[int | None] = mapped_column(Integer)
    langsmith_trace_id: Mapped[str | None] = mapped_column(String(200))
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
