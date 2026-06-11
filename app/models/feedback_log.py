from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FeedbackLog(Base):
    __tablename__ = "feedback_log"
    __table_args__ = (
        Index("idx_feedback_question_log_id", "question_log_id"),
        Index("idx_feedback_type", "feedback_type"),
        Index("idx_feedback_create_time", "create_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    question_log_id: Mapped[int | None] = mapped_column(BigInteger)
    user_id: Mapped[str | None] = mapped_column(String(100))
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500))
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
