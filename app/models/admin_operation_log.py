"""后台审核操作审计日志 ORM（表 admin_operation_log）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AdminOperationLog(Base):
    """记录后台审核与人工标记操作，便于上线前审计追溯。"""

    __tablename__ = "admin_operation_log"
    __table_args__ = (
        Index("idx_admin_op_operation_id", "operation_id", unique=True),
        Index("idx_admin_op_action", "action"),
        Index("idx_admin_op_target", "target_type", "target_id"),
        Index("idx_admin_op_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    operator: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before_snapshot_json: Mapped[str | None] = mapped_column(Text)
    after_snapshot_json: Mapped[str | None] = mapped_column(Text)
    remark: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
