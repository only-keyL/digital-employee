from sqlalchemy import select
from sqlalchemy.orm import Session, load_only

from app.models.question_log import QuestionLog
from app.repositories.base_repository import BaseRepository


class QuestionRepository(BaseRepository[QuestionLog]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, QuestionLog)

    def list_logs(self, *, offset: int = 0, limit: int = 50) -> list[QuestionLog]:
        stmt = (
            select(QuestionLog)
            .options(
                load_only(
                    QuestionLog.id,
                    QuestionLog.request_id,
                    QuestionLog.question_masked,
                    QuestionLog.rewritten_question,
                    QuestionLog.user_id,
                    QuestionLog.group_id,
                    QuestionLog.source_type,
                    QuestionLog.intent,
                    QuestionLog.matched,
                    QuestionLog.similarity_score,
                    QuestionLog.answer,
                    QuestionLog.fallback_reason,
                    QuestionLog.need_human,
                    QuestionLog.risk_level,
                    QuestionLog.latency_ms,
                    QuestionLog.create_time,
                )
            )
            .order_by(QuestionLog.create_time.desc())
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_logs(self) -> int:
        return self.count()

    def count_matched(self) -> int:
        stmt = select(QuestionLog).where(QuestionLog.matched == 1)
        return self.count(stmt)

    def get_log_by_id(self, log_id: int) -> QuestionLog | None:
        return self.session.get(QuestionLog, log_id)

    def create_log(self, log: QuestionLog) -> QuestionLog:
        self.session.add(log)
        self.session.flush()
        return log

    def save(self) -> None:
        self.session.commit()

    def update_langsmith_trace_id(self, log_id: int, trace_id: str) -> None:
        log = self.session.get(QuestionLog, log_id)
        if log is not None:
            log.langsmith_trace_id = trace_id
            self.session.flush()
