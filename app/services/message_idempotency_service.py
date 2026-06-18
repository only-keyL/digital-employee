"""消息幂等服务：仅管理 message_process_log，不耦合具体业务。"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.desensitize import sanitize_dict, sanitize_text
from app.models.message_process_log import MessageProcessLog
from app.repositories.message_process_log_repository import MessageProcessLogRepository

logger = logging.getLogger(__name__)


class MessageIdempotencyService:
    """基于 source + message_id 的消息处理幂等控制。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.repo = MessageProcessLogRepository(session)

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """对消息正文做稳定哈希，用于检测同 message_id 不同内容冲突。"""
        normalized = (content or "").strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def _sanitize_response(response: dict[str, Any]) -> dict[str, Any]:
        """响应摘要脱敏后持久化，避免保存完整知识正文。"""
        safe = sanitize_dict(response)
        if "reply" in safe and isinstance(safe["reply"], str):
            safe["reply"] = sanitize_text(safe["reply"], max_length=200)
        return safe

    def begin_process(
        self,
        *,
        source: str,
        message_id: str,
        content: str,
        group_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """开始处理前检查幂等状态，返回 new / duplicate_success / duplicate_conflict 等。"""
        if not self.settings.message_dedup_enabled:
            return {"status": "new", "record": None}

        content_hash = self.compute_content_hash(content)
        existing = self.repo.get_by_source_message(source, message_id)
        if existing is not None:
            return self._handle_existing(existing, content_hash)

        record = MessageProcessLog(
            source=source,
            message_id=message_id,
            group_id=group_id,
            user_id=user_id,
            content_hash=content_hash,
            status="processing",
        )
        try:
            self.repo.create(record)
            self.session.flush()
        except IntegrityError:
            self.session.rollback()
            existing = self.repo.get_by_source_message(source, message_id)
            if existing is None:
                logger.error("幂等记录并发冲突后仍未查到 source=%s message_id=%s", source, message_id)
                return {"status": "new", "record": None}
            return self._handle_existing(existing, content_hash)
        return {"status": "new", "record": record}

    def _handle_existing(self, existing: MessageProcessLog, content_hash: str) -> dict[str, Any]:
        if existing.content_hash != content_hash:
            return {
                "status": "duplicate_conflict",
                "record": existing,
                "message": "该消息编号已被处理，但本次内容与首次内容不一致，已拒绝重复处理。",
            }
        if existing.status == "success":
            response = {}
            if existing.response_json:
                try:
                    response = json.loads(existing.response_json)
                except json.JSONDecodeError:
                    response = {}
            return {"status": "duplicate_success", "record": existing, "response": response}
        if existing.status == "failed":
            existing.status = "processing"
            existing.error_message = None
            self.repo.save()
            return {"status": "retry_failed", "record": existing}
        return {
            "status": "duplicate_processing",
            "record": existing,
            "message": "该消息正在处理中，请勿重复提交。",
        }

    def mark_success(
        self,
        *,
        source: str,
        message_id: str,
        command: str | None,
        response: dict[str, Any],
    ) -> None:
        """处理成功后写入 success 与脱敏 response 摘要。"""
        if not self.settings.message_dedup_enabled:
            return
        record = self.repo.get_by_source_message(source, message_id)
        if record is None:
            logger.warning("mark_success 时未找到幂等记录 source=%s message_id=%s", source, message_id)
            return
        record.status = "success"
        record.command = command
        record.response_json = json.dumps(self._sanitize_response(response), ensure_ascii=False)
        record.error_message = None
        self.repo.save()

    def mark_failed(self, *, source: str, message_id: str, error_message: str) -> None:
        """处理失败后标记 failed，允许后续 retry_failed 重试。"""
        if not self.settings.message_dedup_enabled:
            return
        record = self.repo.get_by_source_message(source, message_id)
        if record is None:
            return
        record.status = "failed"
        record.error_message = sanitize_text(error_message, max_length=500)
        self.repo.save()
