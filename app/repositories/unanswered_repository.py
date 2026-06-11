from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.unanswered_question import UnansweredQuestion
from app.repositories.base_repository import BaseRepository


class UnansweredRepository(BaseRepository[UnansweredQuestion]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, UnansweredQuestion)

    def get_by_id(self, record_id: int) -> UnansweredQuestion | None:
        return self.session.get(self.model, record_id)

    def list_questions(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        status: str | None = None,
    ) -> list[UnansweredQuestion]:
        stmt = select(UnansweredQuestion)
        if status:
            stmt = stmt.where(UnansweredQuestion.status == status)
        stmt = stmt.order_by(
            UnansweredQuestion.frequency.desc(),
            UnansweredQuestion.last_seen_time.desc(),
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_questions(self, *, status: str | None = None) -> int:
        stmt = select(UnansweredQuestion)
        if status:
            stmt = stmt.where(UnansweredQuestion.status == status)
        return self.count(stmt)

    def top_unanswered(self, limit: int = 10) -> list[UnansweredQuestion]:
        stmt = (
            select(UnansweredQuestion)
            .where(UnansweredQuestion.status == "pending")
            .order_by(
                UnansweredQuestion.frequency.desc(),
                UnansweredQuestion.last_seen_time.desc(),
            )
        )
        return self.list(offset=0, limit=limit, stmt=stmt)

    def get_pending_by_normalized(self, normalized_question: str) -> UnansweredQuestion | None:
        stmt = select(UnansweredQuestion).where(
            UnansweredQuestion.normalized_question == normalized_question,
            UnansweredQuestion.status == "pending",
        )
        return self.session.scalars(stmt).first()

    def get_by_normalized(self, normalized_question: str) -> UnansweredQuestion | None:
        stmt = select(UnansweredQuestion).where(
            UnansweredQuestion.normalized_question == normalized_question,
        )
        return self.session.scalars(stmt).first()

    def create(self, record: UnansweredQuestion) -> UnansweredQuestion:
        now = datetime.now()
        record.last_seen_time = now
        self.session.add(record)
        self.session.flush()
        return record

    def increment_frequency(self, record: UnansweredQuestion, *, question_log_id: int) -> UnansweredQuestion:
        record.frequency += 1
        record.last_seen_time = datetime.now()
        record.question_log_id = question_log_id
        self.session.flush()
        return record

    def mark_converted(self, record: UnansweredQuestion, *, convert_card_id: int) -> UnansweredQuestion:
        record.status = "converted"
        record.convert_card_id = convert_card_id
        self.session.flush()
        return record

    def mark_ignored(self, record: UnansweredQuestion) -> UnansweredQuestion:
        record.status = "ignored"
        self.session.flush()
        return record

    def save(self) -> None:
        self.session.commit()
