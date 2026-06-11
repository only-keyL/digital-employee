from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UnansweredQuestion(Base):
    __tablename__ = "unanswered_question"
    __table_args__ = (
        Index("idx_unanswered_status", "status"),
        Index("idx_unanswered_frequency", "frequency"),
        Index("idx_unanswered_last_seen", "last_seen_time"),
        Index("idx_unanswered_normalized_question", "normalized_question"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_log_id: Mapped[int | None] = mapped_column(BigInteger)
    question: Mapped[str | None] = mapped_column(Text)
    normalized_question: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(String(500))
    system_name: Mapped[str | None] = mapped_column(String(100))
    module_name: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[str | None] = mapped_column(String(500))
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    convert_card_id: Mapped[int | None] = mapped_column(BigInteger)
    last_seen_time: Mapped[datetime | None] = mapped_column(DateTime)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
