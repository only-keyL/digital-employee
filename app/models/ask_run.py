"""Stage3 问答运行记录 ORM（表 ask_run）。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AskRun(Base):
    """一次 AskGraphV2 问答运行记录。"""

    __tablename__ = "ask_run"
    __table_args__ = (
        Index("idx_ask_run_run_id", "run_id", unique=True),
        Index("idx_ask_run_status", "status"),
        Index("idx_ask_run_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    answer: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    top_score: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="api_ask_v2")
    user_id: Mapped[str | None] = mapped_column(String(100))
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
