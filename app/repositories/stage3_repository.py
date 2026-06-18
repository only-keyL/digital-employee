"""Stage3 仓储：ask_run / retrieval_log / llm_call_log / vector_sync_task。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.models.ask_run import AskRun
from app.models.llm_call_log import LlmCallLog
from app.models.retrieval_log import RetrievalLog
from app.models.vector_sync_task import VectorSyncTask
from app.repositories.base_repository import BaseRepository


class AskRunRepository(BaseRepository[AskRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AskRun)

    def get_by_run_id(self, run_id: str) -> AskRun | None:
        stmt = select(AskRun).where(AskRun.run_id == run_id)
        return self.session.scalar(stmt)

    def create(self, record: AskRun) -> AskRun:
        self.session.add(record)
        self.session.flush()
        return record

    def save(self) -> None:
        self.session.flush()


class RetrievalLogRepository(BaseRepository[RetrievalLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RetrievalLog)

    def bulk_create(self, records: list[RetrievalLog]) -> None:
        self.session.add_all(records)
        self.session.flush()


class LlmCallLogRepository(BaseRepository[LlmCallLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, LlmCallLog)

    def create(self, record: LlmCallLog) -> LlmCallLog:
        self.session.add(record)
        self.session.flush()
        return record


class VectorSyncTaskRepository(BaseRepository[VectorSyncTask]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, VectorSyncTask)

    def get_pending_for_knowledge(self, knowledge_id: int) -> VectorSyncTask | None:
        stmt = select(VectorSyncTask).where(
            and_(
                VectorSyncTask.knowledge_id == knowledge_id,
                VectorSyncTask.status.in_(("pending", "running")),
            )
        )
        return self.session.scalar(stmt)

    def list_pending(self, *, limit: int = 20) -> list[VectorSyncTask]:
        stmt = (
            select(VectorSyncTask)
            .where(VectorSyncTask.status == "pending")
            .order_by(VectorSyncTask.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def create(self, task: VectorSyncTask) -> VectorSyncTask:
        self.session.add(task)
        self.session.flush()
        return task

    def save(self) -> None:
        self.session.flush()

    def list_by_status(self, status: str, *, limit: int = 100) -> list[VectorSyncTask]:
        stmt = select(VectorSyncTask).where(VectorSyncTask.status == status).limit(limit)
        return list(self.session.scalars(stmt).all())
