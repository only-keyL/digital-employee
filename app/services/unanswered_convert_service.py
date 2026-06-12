"""Convert unanswered questions to knowledge card drafts or ignore them."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.unanswered_question import UnansweredQuestion
from app.repositories.unanswered_repository import UnansweredRepository
from app.schemas.knowledge_schema import KnowledgeCreate
from app.schemas.unanswered_schema import UnansweredConvertRequest, UnansweredConvertResult
from app.services.knowledge_service import KnowledgeService


class UnansweredConvertError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class UnansweredConvertService:
    """未命中问题转化：转为知识草稿或标记忽略。"""

    VALID_STATUSES = {"pending", "converted", "ignored"}

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = UnansweredRepository(session)
        self.knowledge_service = KnowledgeService(session)

    def get_or_raise(self, unanswered_id: int) -> UnansweredQuestion:
        record = self.repo.get_by_id(unanswered_id)
        if record is None:
            raise UnansweredConvertError("未命中问题不存在")
        return record

    def convert_to_draft(
        self,
        unanswered_id: int,
        payload: UnansweredConvertRequest,
    ) -> UnansweredConvertResult:
        record = self.get_or_raise(unanswered_id)
        if record.status != "pending":
            raise UnansweredConvertError(f"当前状态为 {record.status}，仅 pending 可转为知识卡片")

        knowledge_payload = KnowledgeCreate(
            title=payload.title.strip(),
            question=payload.question.strip(),
            answer=payload.answer.strip(),
            system_name=payload.system_name,
            module_name=payload.module_name,
            tags=payload.tags,
            scene=payload.scene,
            reason_analysis=payload.reason_analysis,
            troubleshooting_steps=payload.troubleshooting_steps,
            solution=payload.solution,
            risk_notice=payload.risk_notice,
            source_group=payload.source_group or "未命中沉淀",
            source_user=payload.source_user or "admin",
        )

        try:
            card_detail = self.knowledge_service.create_draft_without_commit(knowledge_payload)
            card_id = int(card_detail["id"])
            if card_detail.get("audit_status") != "draft":
                raise UnansweredConvertError("转出知识卡片必须为 draft 状态")
            if card_detail.get("vector_status") != "pending":
                raise UnansweredConvertError("转出知识卡片不得同步向量")

            self.repo.mark_converted(record, convert_card_id=card_id)
            self.repo.save()
        except UnansweredConvertError:
            self.session.rollback()
            raise
        except Exception as exc:
            self.session.rollback()
            raise UnansweredConvertError(f"转为知识卡片失败: {exc}") from exc

        return UnansweredConvertResult(
            unanswered_id=record.id,
            convert_card_id=card_id,
            knowledge_card_id=card_id,
            status="converted",
        )

    def ignore(self, unanswered_id: int) -> UnansweredQuestion:
        record = self.get_or_raise(unanswered_id)
        if record.status != "pending":
            raise UnansweredConvertError(f"当前状态为 {record.status}，仅 pending 可忽略")
        self.repo.mark_ignored(record)
        self.repo.save()
        return record
