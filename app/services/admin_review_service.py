"""后台审核与投稿治理服务（阶段 5）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.desensitize import sanitize_text
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.admin_review_repository import AdminReviewRepository
from app.schemas.admin_review_schema import (
    ContributionDetail,
    ContributionListItem,
    ContributionMarkReviewRequest,
    KnowledgeReviewActionRequest,
    PendingKnowledgeDetail,
    PendingKnowledgeListItem,
)
from app.services.admin_operation_log_service import AdminOperationLogService
from app.services.stage3_vector_sync_service import Stage3VectorSyncService

logger = logging.getLogger(__name__)

_PREVIEW_MAX = 120
_PARSED_FIELD_MAX = 300


class AdminReviewServiceError(Exception):
    """后台审核业务异常，message 可直接返回给前端。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AdminReviewService:
    """投稿查看、pending 知识审核、向量同步入队与 contribution 状态联动。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AdminReviewRepository(session)

    @staticmethod
    def _preview_text(text: str | None, *, max_length: int = _PREVIEW_MAX) -> str:
        return sanitize_text(text or "", max_length=max_length)

    @staticmethod
    def _sanitize_parsed_card(parsed: dict[str, Any] | None) -> dict[str, Any] | None:
        if not parsed:
            return None
        return {
            key: sanitize_text(value, max_length=_PARSED_FIELD_MAX) if isinstance(value, str) else value
            for key, value in parsed.items()
        }

    @staticmethod
    def _sanitize_duplicate_result(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not data:
            return None
        result: dict[str, Any] = {}
        for key, value in data.items():
            if key == "matches" and isinstance(value, list):
                result[key] = [
                    {
                        "knowledge_id": item.get("knowledge_id"),
                        "title": sanitize_text(str(item.get("title") or ""), max_length=80),
                        "question_preview": sanitize_text(
                            str(item.get("question_preview") or ""), max_length=80
                        ),
                        "score": item.get("score"),
                        "reason": item.get("reason"),
                    }
                    for item in value[:5]
                    if isinstance(item, dict)
                ]
            elif isinstance(value, dict):
                result[key] = AdminReviewService._sanitize_duplicate_result(value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _sanitize_risk_result(data: dict[str, Any] | None) -> dict[str, Any] | None:
        if not data:
            return None
        hits = data.get("hits") or []
        return {
            "risk_level": data.get("risk_level"),
            "blocked": data.get("blocked"),
            "message": sanitize_text(str(data.get("message") or ""), max_length=200),
            "hits": [sanitize_text(str(h), max_length=120) for h in hits[:10]],
        }

    @staticmethod
    def _parse_json(text: str | None, default: Any) -> Any:
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return default

    def _to_contribution_list_item(self, record: KnowledgeContribution) -> ContributionListItem:
        return ContributionListItem(
            id=record.id,
            contribution_id=record.contribution_id,
            source=record.source,
            message_id=record.message_id,
            group_id=record.group_id,
            user_id=record.user_id,
            user_name=record.user_name,
            status=record.status,
            duplicate_suspected=bool(record.duplicate_suspected),
            risk_level=record.risk_level,
            knowledge_card_id=record.knowledge_card_id,
            content_preview=self._preview_text(record.raw_content),
            created_at=record.created_at,
        )

    def _to_contribution_detail(self, record: KnowledgeContribution) -> ContributionDetail:
        parsed = self._parse_json(record.parsed_card_json, {})
        missing = self._parse_json(record.missing_fields_json, [])
        duplicate = self._parse_json(record.duplicate_result_json, None)
        risk = self._parse_json(record.risk_result_json, None)
        return ContributionDetail(
            id=record.id,
            contribution_id=record.contribution_id,
            source=record.source,
            message_id=record.message_id,
            group_id=record.group_id,
            user_id=record.user_id,
            user_name=record.user_name,
            status=record.status,
            content_preview=self._preview_text(record.raw_content),
            parsed_card=self._sanitize_parsed_card(parsed if isinstance(parsed, dict) else None),
            missing_fields=list(missing) if isinstance(missing, list) else [],
            duplicate_result=self._sanitize_duplicate_result(duplicate if isinstance(duplicate, dict) else None),
            risk_result=self._sanitize_risk_result(risk if isinstance(risk, dict) else None),
            knowledge_card_id=record.knowledge_card_id,
            reject_reason=sanitize_text(record.reject_reason or "", max_length=300) or None,
            duplicate_suspected=bool(record.duplicate_suspected),
            risk_level=record.risk_level,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def list_contributions(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        risk_level: str | None = None,
        duplicate_suspected: bool | None = None,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        records = self.repo.list_contributions(
            offset=offset,
            limit=page_size,
            status=status or None,
            risk_level=risk_level or None,
            duplicate_suspected=duplicate_suspected,
        )
        total = self.repo.count_contributions(
            status=status or None,
            risk_level=risk_level or None,
            duplicate_suspected=duplicate_suspected,
        )
        return {
            "items": [self._to_contribution_list_item(r).model_dump() for r in records],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_contribution_detail(self, contribution_id: str) -> ContributionDetail:
        record = self.repo.get_contribution_by_contribution_id(contribution_id)
        if record is None:
            raise AdminReviewServiceError("投稿记录不存在")
        return self._to_contribution_detail(record)

    def list_pending_knowledge(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        offset = (page - 1) * page_size
        cards = self.repo.list_pending_knowledge(offset=offset, limit=page_size)
        total = self.repo.count_pending_knowledge()
        items: list[dict[str, Any]] = []
        for card in cards:
            contrib = self.repo.get_contribution_by_knowledge_card_id(card.id)
            items.append(
                PendingKnowledgeListItem(
                    id=card.id,
                    title=card.title,
                    system_name=card.system_name,
                    module_name=card.module_name,
                    tags=card.tags,
                    source_group=card.source_group,
                    source_user=card.source_user,
                    audit_status=card.audit_status,
                    vector_status=card.vector_status,
                    contribution_id=contrib.contribution_id if contrib else None,
                    create_time=card.create_time,
                ).model_dump()
            )
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get_pending_knowledge_detail(self, knowledge_id: int) -> PendingKnowledgeDetail:
        card = self.repo.get_knowledge_by_id(knowledge_id)
        if card is None:
            raise AdminReviewServiceError("知识卡片不存在")
        if card.audit_status != "pending":
            raise AdminReviewServiceError("仅待审核知识可在此页面查看与操作")
        contrib = self.repo.get_contribution_by_knowledge_card_id(knowledge_id)
        contrib_item = self._to_contribution_list_item(contrib) if contrib else None
        return PendingKnowledgeDetail(
            id=card.id,
            title=card.title,
            question=card.question,
            answer=card.answer,
            system_name=card.system_name,
            module_name=card.module_name,
            tags=card.tags,
            scene=card.scene,
            reason_analysis=card.reason_analysis,
            troubleshooting_steps=card.troubleshooting_steps,
            solution=card.solution,
            risk_notice=card.risk_notice,
            source_group=card.source_group,
            source_user=card.source_user,
            audit_status=card.audit_status,
            vector_status=card.vector_status,
            enabled=card.enabled,
            contribution=contrib_item,
            create_time=card.create_time,
            update_time=card.update_time,
        )

    def _get_pending_card_or_raise(self, knowledge_id: int) -> KnowledgeCard:
        card = self.repo.get_knowledge_by_id(knowledge_id)
        if card is None:
            raise AdminReviewServiceError("知识卡片不存在")
        if card.audit_status != "pending":
            raise AdminReviewServiceError("仅待审核知识可执行审核操作")
        return card

    def _sync_contribution_status(self, card_id: int, new_status: str) -> None:
        contrib = self.repo.get_contribution_by_knowledge_card_id(card_id)
        if contrib is None:
            return
        contrib.status = new_status
        self.repo.update_contribution(contrib)

    def approve_knowledge(
        self,
        knowledge_id: int,
        payload: KnowledgeReviewActionRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """审核通过：启用知识并入队向量同步，不直接调用 Qdrant。"""
        if payload.action != "approve":
            raise AdminReviewServiceError("请使用 approve 动作审核通过")
        audit_user = payload.audit_user.strip()
        if not audit_user:
            raise AdminReviewServiceError("审核人不能为空")

        card = self._get_pending_card_or_raise(knowledge_id)
        before_snapshot = AdminOperationLogService._card_snapshot(card)
        card.audit_status = "approved"
        card.enabled = 1
        card.audit_user = audit_user
        card.audit_time = datetime.now()
        card.audit_remark = (payload.audit_remark or "").strip() or None
        card.vector_status = "pending"
        card.update_user = audit_user
        self.repo.update_knowledge_card(card)
        self._sync_contribution_status(knowledge_id, "approved")

        vector_task_created = False
        task_id = None
        try:
            task = Stage3VectorSyncService(self.session).enqueue_for_card(knowledge_id, action="upsert")
            if task is not None:
                vector_task_created = True
                task_id = task.id
        except Exception:
            logger.exception("审核通过后入队向量同步失败 knowledge_id=%s", knowledge_id)

        audit_svc = AdminOperationLogService(self.session)
        audit_svc.write_log(
            operator=audit_user,
            action="approve_knowledge",
            target_type="knowledge_card",
            target_id=str(knowledge_id),
            before=before_snapshot,
            after=AdminOperationLogService._card_snapshot(card),
            remark=payload.audit_remark,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.repo.save()
        self.repo.refresh(card)
        logger.info(
            "知识审核通过 knowledge_id=%s audit_user=%s vector_task_id=%s",
            knowledge_id,
            audit_user,
            task_id,
        )
        return {
            "knowledge_id": card.id,
            "audit_status": card.audit_status,
            "enabled": card.enabled,
            "vector_status": card.vector_status,
            "vector_sync_task_created": vector_task_created,
            "vector_sync_task_id": task_id,
            "message": "审核通过，已创建向量同步任务" if vector_task_created else "审核通过",
        }

    def reject_knowledge(
        self,
        knowledge_id: int,
        payload: KnowledgeReviewActionRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """审核拒绝：必须填写原因，不创建 vector_sync_task。"""
        if payload.action != "reject":
            raise AdminReviewServiceError("请使用 reject 动作审核拒绝")
        remark = (payload.audit_remark or "").strip()
        if not remark:
            raise AdminReviewServiceError("审核拒绝时必须填写拒绝原因")
        audit_user = payload.audit_user.strip()
        if not audit_user:
            raise AdminReviewServiceError("审核人不能为空")

        card = self._get_pending_card_or_raise(knowledge_id)
        before_snapshot = AdminOperationLogService._card_snapshot(card)
        card.audit_status = "rejected"
        card.enabled = 0
        card.audit_user = audit_user
        card.audit_time = datetime.now()
        card.audit_remark = remark
        card.vector_status = "rejected"
        card.update_user = audit_user
        self.repo.update_knowledge_card(card)
        self._sync_contribution_status(knowledge_id, "rejected")
        audit_svc = AdminOperationLogService(self.session)
        audit_svc.write_log(
            operator=audit_user,
            action="reject_knowledge",
            target_type="knowledge_card",
            target_id=str(knowledge_id),
            before=before_snapshot,
            after=AdminOperationLogService._card_snapshot(card),
            remark=remark,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.repo.save()
        self.repo.refresh(card)
        logger.info("知识审核拒绝 knowledge_id=%s audit_user=%s", knowledge_id, audit_user)
        return {
            "knowledge_id": card.id,
            "audit_status": card.audit_status,
            "enabled": card.enabled,
            "vector_status": card.vector_status,
            "audit_remark": card.audit_remark,
            "vector_sync_task_created": False,
            "message": "审核已拒绝，未创建向量同步任务",
        }

    def mark_contribution_reviewed(
        self,
        contribution_id: str,
        payload: ContributionMarkReviewRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """人工标记 duplicate_suspected / risk_blocked 投稿，不修改 knowledge_card。"""
        record = self.repo.get_contribution_by_contribution_id(contribution_id)
        if record is None:
            raise AdminReviewServiceError("投稿记录不存在")

        before_snapshot = AdminOperationLogService._contribution_snapshot(record)
        action = payload.action
        if action == "mark_reviewed":
            if record.status not in {"duplicate_suspected", "risk_blocked", "reviewed"}:
                raise AdminReviewServiceError("当前投稿状态不支持 mark_reviewed")
            record.status = "reviewed"
        elif action == "ignore_duplicate":
            if record.status != "duplicate_suspected" and not record.duplicate_suspected:
                raise AdminReviewServiceError("仅重复疑似投稿可标记 ignore_duplicate")
            record.status = "ignore_duplicate"
        elif action == "keep_blocked":
            if record.status != "risk_blocked" and record.risk_level != "high":
                raise AdminReviewServiceError("仅高风险拦截投稿可标记 keep_blocked")
            record.status = "keep_blocked"
        else:
            raise AdminReviewServiceError("不支持的操作类型")

        if payload.remark:
            prefix = f"[{payload.reviewer}] {payload.remark.strip()}"
            record.reject_reason = (record.reject_reason or "") + ("\n" if record.reject_reason else "") + prefix

        audit_action = {
            "mark_reviewed": "mark_contribution_reviewed",
            "ignore_duplicate": "ignore_duplicate",
            "keep_blocked": "keep_blocked",
        }.get(action, action)

        self.repo.update_contribution(record)
        audit_svc = AdminOperationLogService(self.session)
        audit_svc.write_log(
            operator=payload.reviewer.strip() or "unknown",
            action=audit_action,
            target_type="contribution",
            target_id=contribution_id,
            before=before_snapshot,
            after=AdminOperationLogService._contribution_snapshot(record),
            remark=payload.remark,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.repo.save()
        self.repo.refresh(record)
        return {
            "contribution_id": record.contribution_id,
            "status": record.status,
            "message": "投稿已人工标记",
        }

    def count_pending_knowledge(self) -> int:
        return self.repo.count_pending_knowledge()
