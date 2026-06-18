"""知识投稿 ORM（表 knowledge_contribution）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KnowledgeContribution(Base):
    """用户通过企微沉淀提交的知识投稿记录。"""

    __tablename__ = "knowledge_contribution"
    __table_args__ = (
        Index("idx_contribution_id", "contribution_id", unique=True),
        Index("idx_contribution_status", "status"),
        Index("idx_contribution_user", "user_id"),
        Index("idx_contribution_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contribution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="mock_wecom")
    message_id: Mapped[str | None] = mapped_column(String(64))
    group_id: Mapped[str | None] = mapped_column(String(100))
    user_id: Mapped[str] = mapped_column(String(100), nullable=False)
    user_name: Mapped[str | None] = mapped_column(String(100))
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_card_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    completeness_score: Mapped[float | None] = mapped_column(Float)
    missing_fields_json: Mapped[str | None] = mapped_column(Text)
    duplicate_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_result_json: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="none")
    risk_result_json: Mapped[str | None] = mapped_column(Text)
    knowledge_card_id: Mapped[int | None] = mapped_column(Integer)
    graph_run_id: Mapped[str | None] = mapped_column(String(64))
    reject_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
