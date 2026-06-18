from datetime import datetime
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.knowledge_card import KnowledgeCard
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.knowledge_schema import KnowledgeAuditRequest, KnowledgeCreate, KnowledgeUpdate
from app.services.knowledge_content import card_to_content_dict, compute_content_hash

DEFAULT_OPERATOR = "admin"
logger = logging.getLogger(__name__)


class KnowledgeServiceError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class KnowledgeService:
    """知识卡片 CRUD、审核流转与向量同步编排。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = KnowledgeRepository(session)

    def _get_active_or_raise(self, card_id: int) -> KnowledgeCard:
        card = self.repo.get_active_by_id(card_id)
        if card is None:
            raise KnowledgeServiceError("知识卡片不存在")
        return card

    def _apply_form_fields(self, card: KnowledgeCard, data: dict[str, Any]) -> None:
        card.title = data["title"].strip()
        card.question = data["question"].strip()
        card.answer = data["answer"].strip()
        card.system_name = (data.get("system_name") or "").strip() or None
        card.module_name = (data.get("module_name") or "").strip() or None
        card.tags = (data.get("tags") or "").strip() or None
        card.scene = (data.get("scene") or "").strip() or None
        card.reason_analysis = (data.get("reason_analysis") or "").strip() or None
        card.troubleshooting_steps = (data.get("troubleshooting_steps") or "").strip() or None
        card.solution = (data.get("solution") or "").strip() or None
        card.risk_notice = (data.get("risk_notice") or "").strip() or None
        card.source_group = (data.get("source_group") or "").strip() or None
        card.source_user = (data.get("source_user") or "").strip() or None

    def _to_detail_dict(self, card: KnowledgeCard) -> dict[str, Any]:
        return {
            "id": card.id,
            "title": card.title,
            "question": card.question,
            "answer": card.answer,
            "system_name": card.system_name or "",
            "module_name": card.module_name or "",
            "tags": card.tags or "",
            "scene": card.scene or "",
            "reason_analysis": card.reason_analysis or "",
            "troubleshooting_steps": card.troubleshooting_steps or "",
            "solution": card.solution or "",
            "risk_notice": card.risk_notice or "",
            "source_group": card.source_group or "",
            "source_user": card.source_user or "",
            "audit_status": card.audit_status,
            "audit_user": card.audit_user,
            "audit_time": card.audit_time,
            "audit_remark": card.audit_remark,
            "vector_status": card.vector_status,
            "vector_id": card.vector_id,
            "vector_error": card.vector_error,
            "content_hash": card.content_hash,
            "version": card.version,
            "enabled": card.enabled,
            "deleted": card.deleted,
            "create_user": card.create_user,
            "update_user": card.update_user,
            "create_time": card.create_time,
            "update_time": card.update_time,
        }

    def _apply_vector_sync(self, card_id: int) -> None:
        """审核通过后异步入队向量同步，不阻塞接口。"""
        try:
            from app.services.stage3_vector_sync_service import Stage3VectorSyncService

            Stage3VectorSyncService(self.session).enqueue_for_card(card_id)
            self.repo.save()
        except Exception:
            logger.exception("入队向量同步任务失败 card_id=%s", card_id)
            self.repo.save()

    def list_for_page(self, *, page: int = 1, page_size: int = 20) -> dict:
        offset = (page - 1) * page_size
        items = self.repo.list_cards(offset=offset, limit=page_size)
        total = self.repo.count_cards()
        return {
            "items": [self._to_detail_dict(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def list_api(self, *, page: int = 1, page_size: int = 20) -> dict:
        return self.list_for_page(page=page, page_size=page_size)

    def get_detail(self, card_id: int) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def _build_draft_card(
        self,
        payload: KnowledgeCreate | dict[str, Any],
        operator: str = DEFAULT_OPERATOR,
    ) -> KnowledgeCard:
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        card = KnowledgeCard(
            audit_status="draft",
            vector_status="pending",
            enabled=1,
            deleted=0,
            version=1,
            create_user=operator,
            update_user=operator,
        )
        self._apply_form_fields(card, data)
        card.content_hash = compute_content_hash(card_to_content_dict(card))
        self.repo.add(card)
        return card

    def create_draft_without_commit(
        self,
        payload: KnowledgeCreate | dict[str, Any],
        operator: str = DEFAULT_OPERATOR,
    ) -> dict[str, Any]:
        """Create draft knowledge card and flush; caller commits with unanswered update."""
        card = self._build_draft_card(payload, operator=operator)
        self.repo.refresh(card)
        return self._to_detail_dict(card)

    def create(
        self,
        payload: KnowledgeCreate | dict[str, Any],
        operator: str = DEFAULT_OPERATOR,
    ) -> dict[str, Any]:
        card = self._build_draft_card(payload, operator=operator)
        self.repo.save()
        self.repo.refresh(card)
        return self._to_detail_dict(card)

    def update(
        self,
        card_id: int,
        payload: KnowledgeUpdate | dict[str, Any],
        operator: str = DEFAULT_OPERATOR,
    ) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        was_approved = card.audit_status == "approved"
        self._apply_form_fields(card, data)
        card.update_user = operator
        card.content_hash = compute_content_hash(card_to_content_dict(card))
        if was_approved:
            card.version += 1
            card.vector_status = "pending"
        self.repo.save()
        self.repo.refresh(card)
        if was_approved:
            self._apply_vector_sync(card_id)
            card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def submit_audit(self, card_id: int, operator: str = DEFAULT_OPERATOR) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        if card.audit_status not in {"draft", "rejected"}:
            raise KnowledgeServiceError("当前状态不允许提交审核")
        if not card.title or not card.question or not card.answer:
            raise KnowledgeServiceError("提交审核前请填写标题、标准问题和标准答案")
        card.audit_status = "pending"
        card.update_user = operator
        self.repo.save()
        self.repo.refresh(card)
        return self._to_detail_dict(card)

    def audit(self, card_id: int, payload: KnowledgeAuditRequest) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        if card.audit_status != "pending":
            raise KnowledgeServiceError("审核状态非法，仅待审核卡片可审核")
        if payload.audit_status == "rejected" and not (payload.audit_remark and payload.audit_remark.strip()):
            raise KnowledgeServiceError("审核拒绝时必须填写审核备注")
        card.audit_status = payload.audit_status
        card.audit_user = payload.audit_user
        card.audit_time = datetime.now()
        card.audit_remark = payload.audit_remark
        card.update_user = payload.audit_user
        self.repo.save()
        self.repo.refresh(card)
        self._apply_vector_sync(card_id)
        card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def enable(self, card_id: int, operator: str = DEFAULT_OPERATOR) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        card.enabled = 1
        card.update_user = operator
        self.repo.save()
        self.repo.refresh(card)
        self._apply_vector_sync(card_id)
        card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def disable(self, card_id: int, operator: str = DEFAULT_OPERATOR) -> dict[str, Any]:
        card = self._get_active_or_raise(card_id)
        card.enabled = 0
        card.update_user = operator
        self.repo.save()
        self.repo.refresh(card)
        self._apply_vector_sync(card_id)
        card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def soft_delete(self, card_id: int, operator: str = DEFAULT_OPERATOR) -> None:
        card = self._get_active_or_raise(card_id)
        card.deleted = 1
        card.enabled = 0
        card.update_user = operator
        self.repo.save()
        self._apply_vector_sync(card_id)

    def sync_vector(self, card_id: int) -> dict[str, Any]:
        self._get_active_or_raise(card_id)
        self._apply_vector_sync(card_id)
        card = self._get_active_or_raise(card_id)
        return self._to_detail_dict(card)

    def create_seed_card(self, data: dict[str, Any], operator: str = DEFAULT_OPERATOR) -> KnowledgeCard | None:
        existing = self.repo.get_by_title(data["title"])
        if existing is not None:
            return None
        card = KnowledgeCard(
            title=data["title"],
            question=data["question"],
            answer=data["answer"],
            system_name=data.get("system_name"),
            module_name=data.get("module_name"),
            tags=data.get("tags"),
            scene=data.get("scene"),
            reason_analysis=data.get("reason_analysis"),
            troubleshooting_steps=data.get("troubleshooting_steps"),
            solution=data.get("solution"),
            risk_notice=data.get("risk_notice"),
            source_group=data.get("source_group", "实施群"),
            source_user=data.get("source_user", operator),
            audit_status=data.get("audit_status", "approved"),
            audit_user=operator,
            audit_time=datetime.now(),
            audit_remark=data.get("audit_remark", "演示数据"),
            vector_status="pending",
            enabled=1,
            deleted=0,
            version=1,
            create_user=operator,
            update_user=operator,
        )
        card.content_hash = compute_content_hash(card_to_content_dict(card))
        self.repo.add(card)
        return card
