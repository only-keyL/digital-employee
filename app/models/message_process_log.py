"""消息处理幂等记录 ORM（表 message_process_log）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MessageProcessLog(Base):
    """按 source + message_id 记录消息处理结果，支撑 mock_wecom 等入口幂等。"""

    __tablename__ = "message_process_log"
    __table_args__ = (
        UniqueConstraint("source", "message_id", name="uk_message_process_source_mid"),
        Index("idx_message_process_status", "status"),
        Index("idx_message_process_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    group_id: Mapped[str | None] = mapped_column(String(100))
    user_id: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    command: Mapped[str | None] = mapped_column(String(32))
    response_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
