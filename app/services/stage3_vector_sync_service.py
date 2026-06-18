"""Stage3 向量同步任务服务：异步入队 + worker 执行。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.models.knowledge_card import KnowledgeCard
from app.models.vector_sync_task import VectorSyncTask
from app.rag.qdrant_vector_store import QdrantVectorStore, get_qdrant_vector_store
from app.rag.vector_payload_builder import build_qdrant_payload, build_vector_text, is_sync_eligible
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.stage3_repository import VectorSyncTaskRepository
from app.services.vector_sync_service import should_index_card

logger = logging.getLogger(__name__)


class Stage3VectorSyncService:
    """管理 vector_sync_task：审核通过知识异步入队，worker 异步同步 Qdrant。"""

    def __init__(
        self,
        session: Session,
        *,
        embedding_client: EmbeddingClient | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.knowledge_repo = KnowledgeRepository(session)
        self.task_repo = VectorSyncTaskRepository(session)
        self.embedding = embedding_client or EmbeddingClient(self.settings)
        self.store = vector_store or get_qdrant_vector_store()

    def enqueue_for_card(self, card_id: int, *, action: str | None = None) -> VectorSyncTask | None:
        """为知识卡片创建同步任务；已有 pending/running 时不重复创建。"""
        card = self.knowledge_repo.get_by_id(card_id)
        if card is None:
            return None

        existing = self.task_repo.get_pending_for_knowledge(card_id)
        if existing is not None:
            return existing

        task_action = action or ("upsert" if should_index_card(card) else "delete")
        task = VectorSyncTask(
            knowledge_id=card_id,
            action=task_action,
            status="pending",
            max_retries=3,
        )
        return self.task_repo.create(task)

    def enqueue_all_approved(self, *, force_resync: bool = False) -> int:
        """批量入队待同步的 approved 知识。"""
        cards = self.knowledge_repo.list_approved_enabled()
        count = 0
        for card in cards:
            vs = (card.vector_status or "").strip()
            need_sync = force_resync or vs in {"", "pending", "failed"} or vs != "synced"
            if need_sync:
                task = self.enqueue_for_card(card.id)
                if task is not None:
                    count += 1
        self.session.flush()
        return count

    async def process_pending(self, *, limit: int = 20, dry_run: bool = False) -> dict[str, int]:
        """执行 pending 任务，返回 success/failed/skipped 统计。"""
        tasks = self.task_repo.list_pending(limit=limit)
        stats = {"success": 0, "failed": 0, "skipped": 0, "total": len(tasks)}

        for task in tasks:
            if dry_run:
                stats["skipped"] += 1
                continue
            task.status = "running"
            task.last_run_at = datetime.utcnow()
            self.task_repo.save()

            try:
                result = await self._execute_task(task)
                stats[result] += 1
            except Exception as exc:
                logger.error("向量同步任务失败 task_id=%s：%s", task.id, exc)
                self._mark_failed(task, str(exc))
                stats["failed"] += 1

        if not dry_run:
            self.session.commit()
        return stats

    async def _execute_task(self, task: VectorSyncTask) -> str:
        card = self.knowledge_repo.get_by_id(task.knowledge_id)
        if card is None:
            task.status = "skipped"
            task.error_message = "知识卡片不存在"
            self.task_repo.save()
            return "skipped"

        if task.action == "delete" or not is_sync_eligible(card):
            if not is_sync_eligible(card) and task.action == "upsert":
                task.status = "skipped"
                task.error_message = "未审核/未启用/已删除，跳过 upsert"
                self.task_repo.save()
                return "skipped"

            self.store.delete_knowledge(card.id)
            card.vector_status = "pending"
            card.vector_id = None
            card.vector_error = None
            task.status = "success"
            task.error_message = None
            self.task_repo.save()
            return "success"

        vector_text = build_vector_text(card)
        vector = await self.embedding.embed_text(vector_text)
        payload = build_qdrant_payload(card)
        self.store.upsert_knowledge(card.id, vector, payload)

        card.vector_status = "synced"
        card.vector_id = str(card.id)
        card.vector_error = None
        task.status = "success"
        task.error_message = None
        self.task_repo.save()
        return "success"

    def _mark_failed(self, task: VectorSyncTask, message: str) -> None:
        task.retry_count += 1
        task.error_message = message[:2000]
        task.last_run_at = datetime.utcnow()
        if task.retry_count >= task.max_retries:
            task.status = "failed"
            card = self.knowledge_repo.get_by_id(task.knowledge_id)
            if card is not None:
                card.vector_status = "failed"
                card.vector_error = message[:2000]
        else:
            task.status = "pending"
            task.next_retry_at = datetime.utcnow() + timedelta(minutes=task.retry_count * 5)
        self.task_repo.save()
