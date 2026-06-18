"""后台操作审计日志服务。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.desensitize import sanitize_text
from app.models.admin_operation_log import AdminOperationLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.admin_operation_log_repository import AdminOperationLogRepository

logger = logging.getLogger(__name__)


class AdminOperationLogService:
    """写入与查询 admin_operation_log，快照字段脱敏。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = AdminOperationLogRepository(session)

    @staticmethod
    def _card_snapshot(card: KnowledgeCard | None) -> dict[str, Any] | None:
        if card is None:
            return None
        return {
            "id": card.id,
            "audit_status": card.audit_status,
            "enabled": card.enabled,
            "vector_status": card.vector_status,
            "title_preview": sanitize_text(card.title or "", max_length=80),
        }

    @staticmethod
    def _contribution_snapshot(contrib: KnowledgeContribution | None) -> dict[str, Any] | None:
        if contrib is None:
            return None
        return {
            "contribution_id": contrib.contribution_id,
            "status": contrib.status,
            "knowledge_card_id": contrib.knowledge_card_id,
            "duplicate_suspected": bool(contrib.duplicate_suspected),
            "risk_level": contrib.risk_level,
        }

    def write_log(
        self,
        *,
        operator: str,
        action: str,
        target_type: str,
        target_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        remark: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AdminOperationLog:
        """写入一条审计日志；与审核主事务同一 session，由调用方 commit。"""
        record = AdminOperationLog(
            operation_id=str(uuid.uuid4()),
            operator=operator,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            before_snapshot_json=json.dumps(before or {}, ensure_ascii=False),
            after_snapshot_json=json.dumps(after or {}, ensure_ascii=False),
            remark=sanitize_text(remark or "", max_length=500) or None,
            ip_address=ip_address,
            user_agent=sanitize_text(user_agent or "", max_length=200) or None,
        )
        try:
            return self.repo.create(record)
        except Exception:
            logger.exception(
                "写入审计日志失败 action=%s target=%s/%s",
                action,
                target_type,
                target_id,
            )
            raise

    def list_logs(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        operator: str | None = None,
        action: str | None = None,
        target_type: str | None = None,
    ) -> dict[str, Any]:
        offset = (page - 1) * page_size
        items = self.repo.list_logs(
            offset=offset,
            limit=page_size,
            operator=operator or None,
            action=action or None,
            target_type=target_type or None,
        )
        total = self.repo.count_logs(
            operator=operator or None,
            action=action or None,
            target_type=target_type or None,
        )
        return {
            "items": [self._to_dict(item) for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_detail(self, operation_id: str) -> dict[str, Any] | None:
        record = self.repo.get_by_operation_id(operation_id)
        if record is None:
            return None
        return self._to_dict(record)

    @staticmethod
    def _to_dict(record: AdminOperationLog) -> dict[str, Any]:
        before = {}
        after = {}
        try:
            before = json.loads(record.before_snapshot_json or "{}")
        except json.JSONDecodeError:
            before = {}
        try:
            after = json.loads(record.after_snapshot_json or "{}")
        except json.JSONDecodeError:
            after = {}
        return {
            "id": record.id,
            "operation_id": record.operation_id,
            "operator": record.operator,
            "action": record.action,
            "target_type": record.target_type,
            "target_id": record.target_id,
            "before_snapshot": before,
            "after_snapshot": after,
            "remark": record.remark,
            "ip_address": record.ip_address,
            "user_agent": record.user_agent,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
