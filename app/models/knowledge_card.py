from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KnowledgeCard(Base):
    __tablename__ = "knowledge_card"
    __table_args__ = (
        Index("idx_knowledge_audit_enabled", "audit_status", "enabled"),
        Index("idx_knowledge_vector_status", "vector_status"),
        Index("idx_knowledge_deleted", "deleted"),
        Index("idx_knowledge_system_module", "system_name", "module_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    question: Mapped[str | None] = mapped_column(Text)
    answer: Mapped[str | None] = mapped_column(Text)
    system_name: Mapped[str | None] = mapped_column(String(100))
    module_name: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[str | None] = mapped_column(String(500))
    scene: Mapped[str | None] = mapped_column(String(500))
    reason_analysis: Mapped[str | None] = mapped_column(Text)
    troubleshooting_steps: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)
    risk_notice: Mapped[str | None] = mapped_column(Text)
    source_group: Mapped[str | None] = mapped_column(String(100))
    source_user: Mapped[str | None] = mapped_column(String(100))
    audit_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    audit_user: Mapped[str | None] = mapped_column(String(100))
    audit_time: Mapped[datetime | None] = mapped_column(DateTime)
    audit_remark: Mapped[str | None] = mapped_column(String(500))
    vector_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    vector_id: Mapped[str | None] = mapped_column(String(100))
    vector_error: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    create_user: Mapped[str | None] = mapped_column(String(100))
    update_user: Mapped[str | None] = mapped_column(String(100))
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
