"""用户反馈数据访问层。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.feedback_log import FeedbackLog
from app.models.question_log import QuestionLog
from app.repositories.base_repository import BaseRepository


class FeedbackRepository(BaseRepository[FeedbackLog]):
    """feedback_log 表查询与统计。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, FeedbackLog)

    def get_by_question_log_id(self, question_log_id: int) -> FeedbackLog | None:
        stmt = select(FeedbackLog).where(FeedbackLog.question_log_id == question_log_id)
        return self.session.scalars(stmt).first()

    def list_feedback(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        feedback_type: str | None = None,
    ) -> list[FeedbackLog]:
        stmt = select(FeedbackLog)
        if feedback_type:
            stmt = stmt.where(FeedbackLog.feedback_type == feedback_type)
        stmt = stmt.order_by(FeedbackLog.create_time.desc())
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_feedback(self, *, feedback_type: str | None = None) -> int:
        stmt = select(FeedbackLog)
        if feedback_type:
            stmt = stmt.where(FeedbackLog.feedback_type == feedback_type)
        return self.count(stmt)

    def count_by_type(self, feedback_type: str) -> int:
        stmt = select(FeedbackLog).where(FeedbackLog.feedback_type == feedback_type)
        return self.count(stmt)

    def create(self, record: FeedbackLog) -> FeedbackLog:
        self.session.add(record)
        self.session.flush()
        return record

    def save(self) -> None:
        self.session.commit()

    def list_with_question_summary(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        feedback_type: str | None = None,
    ) -> list[tuple[FeedbackLog, str | None]]:
        stmt = (
            select(FeedbackLog, QuestionLog.question_masked)
            .outerjoin(QuestionLog, FeedbackLog.question_log_id == QuestionLog.id)
        )
        if feedback_type:
            stmt = stmt.where(FeedbackLog.feedback_type == feedback_type)
        stmt = stmt.order_by(FeedbackLog.create_time.desc()).offset(offset).limit(limit)
        return list(self.session.execute(stmt).all())

    def top_negative_feedback(self, limit: int = 10) -> list[dict]:
        """统计「无用」反馈最多的问题摘要（看板用）。"""
        stmt = (
            select(
                QuestionLog.question_masked.label("question_summary"),
                func.count(FeedbackLog.id).label("negative_count"),
                func.max(FeedbackLog.create_time).label("last_feedback_time"),
            )
            .join(QuestionLog, FeedbackLog.question_log_id == QuestionLog.id)
            .where(FeedbackLog.feedback_type == "useless")
            .group_by(QuestionLog.question_masked)
            .order_by(func.count(FeedbackLog.id).desc(), func.max(FeedbackLog.create_time).desc())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        result: list[dict] = []
        for row in rows:
            summary = (row.question_summary or "").strip()
            if len(summary) > 80:
                summary = summary[:80] + "..."
            result.append(
                {
                    "question_summary": summary,
                    "negative_count": int(row.negative_count or 0),
                    "last_feedback_time": row.last_feedback_time,
                }
            )
        return result
