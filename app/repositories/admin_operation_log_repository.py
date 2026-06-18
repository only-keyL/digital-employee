"""admin_operation_log 数据访问层。"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.admin_operation_log import AdminOperationLog
from app.repositories.base_repository import BaseRepository


class AdminOperationLogRepository(BaseRepository[AdminOperationLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AdminOperationLog)

    def create(self, record: AdminOperationLog) -> AdminOperationLog:
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_operation_id(self, operation_id: str) -> AdminOperationLog | None:
        stmt = select(AdminOperationLog).where(AdminOperationLog.operation_id == operation_id)
        return self.session.scalar(stmt)

    def list_logs(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        operator: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
    ) -> list[AdminOperationLog]:
        stmt = select(AdminOperationLog).order_by(desc(AdminOperationLog.created_at))
        if operator:
            stmt = stmt.where(AdminOperationLog.operator == operator)
        if action:
            stmt = stmt.where(AdminOperationLog.action == action)
        if target_type:
            stmt = stmt.where(AdminOperationLog.target_type == target_type)
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_logs(
        self,
        *,
        operator: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
    ) -> int:
        stmt = select(AdminOperationLog)
        if operator:
            stmt = stmt.where(AdminOperationLog.operator == operator)
        if action:
            stmt = stmt.where(AdminOperationLog.action == action)
        if target_type:
            stmt = stmt.where(AdminOperationLog.target_type == target_type)
        return self.count(stmt)

    def save(self) -> None:
        self.session.flush()
