"""message_process_log 数据访问层。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message_process_log import MessageProcessLog
from app.repositories.base_repository import BaseRepository


class MessageProcessLogRepository(BaseRepository[MessageProcessLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MessageProcessLog)

    def get_by_source_message(self, source: str, message_id: str) -> MessageProcessLog | None:
        stmt = select(MessageProcessLog).where(
            MessageProcessLog.source == source,
            MessageProcessLog.message_id == message_id,
        )
        return self.session.scalar(stmt)

    def create(self, record: MessageProcessLog) -> MessageProcessLog:
        self.session.add(record)
        self.session.flush()
        return record

    def save(self) -> None:
        self.session.flush()
