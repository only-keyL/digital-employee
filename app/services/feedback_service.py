from sqlalchemy.orm import Session

from app.models.feedback_log import FeedbackLog
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.question_repository import QuestionRepository
from app.schemas.feedback_schema import FeedbackCreateRequest, VALID_FEEDBACK_TYPES


class FeedbackServiceError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class FeedbackService:
    """用户问答反馈（点赞/点踩等）提交与查询。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = FeedbackRepository(session)
        self.question_repo = QuestionRepository(session)

    @staticmethod
    def _truncate_summary(text: str | None, limit: int = 80) -> str:
        value = (text or "").strip()
        if len(value) <= limit:
            return value
        return value[:limit] + "..."

    def _to_detail(self, item: FeedbackLog, question_summary: str = "") -> dict:
        return {
            "id": item.id,
            "question_log_id": item.question_log_id,
            "user_id": item.user_id or "anonymous",
            "feedback_type": item.feedback_type,
            "comment": item.comment or "",
            "create_time": item.create_time,
            "question_summary": question_summary,
        }

    def submit_feedback(self, payload: FeedbackCreateRequest) -> dict:
        if payload.feedback_type not in VALID_FEEDBACK_TYPES:
            raise FeedbackServiceError("反馈类型非法")

        question_log = self.question_repo.get_log_by_id(payload.question_log_id)
        if question_log is None:
            raise FeedbackServiceError("提问日志不存在")

        existing = self.repo.get_by_question_log_id(payload.question_log_id)
        if existing is not None:
            raise FeedbackServiceError("该提问已提交过反馈")

        record = FeedbackLog(
            question_log_id=payload.question_log_id,
            user_id=(payload.user_id or "anonymous").strip() or "anonymous",
            feedback_type=payload.feedback_type,
            comment=payload.comment,
        )
        self.repo.create(record)
        self.repo.save()
        summary = self._truncate_summary(question_log.question_masked)
        return self._to_detail(record, question_summary=summary)

    def list_for_api(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        feedback_type: str | None = None,
    ) -> dict:
        if feedback_type and feedback_type not in VALID_FEEDBACK_TYPES:
            raise FeedbackServiceError("反馈类型非法")

        offset = (page - 1) * page_size
        rows = self.repo.list_with_question_summary(
            offset=offset,
            limit=page_size,
            feedback_type=feedback_type,
        )
        total = self.repo.count_feedback(feedback_type=feedback_type)
        items = [
            self._to_detail(item, question_summary=self._truncate_summary(summary))
            for item, summary in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_for_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        feedback_type: str | None = None,
    ) -> dict:
        result = self.list_for_api(page=page, page_size=page_size, feedback_type=feedback_type)
        result["feedback_type_filter"] = feedback_type or ""
        return result
