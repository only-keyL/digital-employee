from sqlalchemy.orm import Session

from app.models.unanswered_question import UnansweredQuestion
from app.repositories.unanswered_repository import UnansweredRepository
from app.schemas.unanswered_schema import UnansweredDetail
from app.services.unanswered_convert_service import UnansweredConvertError, UnansweredConvertService
from app.services.unanswered_draft_service import UnansweredDraftService


class UnansweredService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = UnansweredRepository(session)
        self.convert_service = UnansweredConvertService(session)
        self.draft_service = UnansweredDraftService()

    def _to_detail(self, item: UnansweredQuestion) -> dict:
        detail = UnansweredDetail(
            id=item.id,
            question=item.question or "",
            normalized_question=item.normalized_question or "",
            summary=item.summary or "",
            system_name=item.system_name or "",
            module_name=item.module_name or "",
            tags=item.tags or "",
            frequency=item.frequency,
            status=item.status,
            question_log_id=item.question_log_id,
            convert_card_id=item.convert_card_id,
            last_seen_time=item.last_seen_time,
            create_time=item.create_time,
            update_time=item.update_time,
        )
        return detail.model_dump()

    def list_for_api(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> dict:
        offset = (page - 1) * page_size
        items = self.repo.list_questions(offset=offset, limit=page_size, status=status)
        total = self.repo.count_questions(status=status)
        return {
            "items": [self._to_detail(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_for_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = "pending",
    ) -> dict:
        result = self.list_for_api(page=page, page_size=page_size, status=status)
        result["status_filter"] = status or ""
        return result

    def get_detail(self, unanswered_id: int) -> dict:
        record = self.convert_service.get_or_raise(unanswered_id)
        return self._to_detail(record)

    def get_detail_for_page(self, unanswered_id: int) -> dict | None:
        record = self.repo.get_by_id(unanswered_id)
        if record is None:
            return None
        return self._to_detail(record)

    def generate_draft_preview(self, unanswered_id: int) -> dict:
        record = self.convert_service.get_or_raise(unanswered_id)
        if record.status != "pending":
            raise UnansweredConvertError(f"当前状态为 {record.status}，仅 pending 可生成草稿预览")
        preview = self.draft_service.generate_preview(record)
        return preview.model_dump()

    def convert_to_draft(self, unanswered_id: int, payload) -> dict:
        result = self.convert_service.convert_to_draft(unanswered_id, payload)
        return result.model_dump()

    def ignore(self, unanswered_id: int) -> dict:
        record = self.convert_service.ignore(unanswered_id)
        return self._to_detail(record)
