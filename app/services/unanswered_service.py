"""未命中问题业务服务（列表、详情、草稿预览、转化、忽略）。"""

from sqlalchemy.orm import Session

from app.models.unanswered_question import UnansweredQuestion
from app.repositories.unanswered_repository import UnansweredRepository
from app.schemas.unanswered_schema import UnansweredDetail
from app.services.unanswered_convert_service import UnansweredConvertError, UnansweredConvertService
from app.services.unanswered_draft_service import UnansweredDraftService


class UnansweredService:
    """未命中问题聚合服务，协调仓储、草稿生成与转化逻辑。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = UnansweredRepository(session)  # 未命中问题仓储
        self.convert_service = UnansweredConvertService(session)  # 转化/忽略
        self.draft_service = UnansweredDraftService()  # 草稿预览生成

    def _to_detail(self, item: UnansweredQuestion) -> dict:
        """ORM 实体转 API 详情字典。"""
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
        """API 分页列表。"""
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
        """管理后台分页列表（含 status_filter）。"""
        result = self.list_for_api(page=page, page_size=page_size, status=status)
        result["status_filter"] = status or ""
        return result

    def get_detail(self, unanswered_id: int) -> dict:
        """API 详情（不存在则抛 UnansweredConvertError）。"""
        record = self.convert_service.get_or_raise(unanswered_id)
        return self._to_detail(record)

    def get_detail_for_page(self, unanswered_id: int) -> dict | None:
        """页面详情（不存在返回 None）。"""
        record = self.repo.get_by_id(unanswered_id)
        if record is None:
            return None
        return self._to_detail(record)

    def generate_draft_preview(self, unanswered_id: int) -> dict:
        """为 pending 状态未命中问题生成草稿预览。"""
        record = self.convert_service.get_or_raise(unanswered_id)
        if record.status != "pending":
            raise UnansweredConvertError(f"当前状态为 {record.status}，仅 pending 可生成草稿预览")
        preview = self.draft_service.generate_preview(record)
        return preview.model_dump()

    def convert_to_draft(self, unanswered_id: int, payload) -> dict:
        """将未命中问题转为 draft 知识卡片。"""
        result = self.convert_service.convert_to_draft(unanswered_id, payload)
        return result.model_dump()

    def ignore(self, unanswered_id: int) -> dict:
        """忽略未命中问题。"""
        record = self.convert_service.ignore(unanswered_id)
        return self._to_detail(record)
