"""Synchronize knowledge cards between MySQL and Qdrant."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.knowledge_card import KnowledgeCard
from app.rag.qdrant_store import QdrantStore, get_qdrant_store
from app.repositories.knowledge_repository import KnowledgeRepository


def should_index_card(card: KnowledgeCard) -> bool:
    return card.deleted == 0 and card.audit_status == "approved" and card.enabled == 1


class VectorSyncService:
    def __init__(
        self,
        session: Session,
        *,
        qdrant_store: QdrantStore | None = None,
    ) -> None:
        self.session = session
        self.repo = KnowledgeRepository(session)
        self.qdrant = qdrant_store or get_qdrant_store()

    def sync_card(self, card_id: int) -> KnowledgeCard:
        card = self.repo.get_by_id(card_id)
        if card is None:
            raise ValueError(f"知识卡片不存在: {card_id}")
        return self._sync_card_record(card)

    def _sync_card_record(self, card: KnowledgeCard) -> KnowledgeCard:
        if should_index_card(card):
            try:
                self.qdrant.upsert_knowledge_card(card)
                card.vector_status = "synced"
                card.vector_id = str(card.id)
                card.vector_error = None
            except Exception as exc:
                card.vector_status = "failed"
                card.vector_error = str(exc)
        else:
            try:
                self.qdrant.delete_knowledge_card(card.id)
            except Exception as exc:
                card.vector_status = "failed"
                card.vector_error = f"删除向量失败: {exc}"
                self.session.flush()
                return card
            card.vector_status = "pending"
            card.vector_id = None
            card.vector_error = None
        self.session.flush()
        return card

    def delete_card_vector(self, card_id: int) -> None:
        card = self.repo.get_by_id(card_id)
        if card is None:
            return
        try:
            self.qdrant.delete_knowledge_card(card_id)
        except Exception as exc:
            card.vector_status = "failed"
            card.vector_error = f"删除向量失败: {exc}"
            self.session.flush()
            return
        card.vector_status = "pending"
        card.vector_id = None
        card.vector_error = None
        self.session.flush()

    def rebuild_all(self, *, recreate: bool = False) -> dict[str, int]:
        self.qdrant.init_collection(recreate=recreate)
        cards = self.repo.list_approved_enabled()
        synced = 0
        failed = 0
        for card in cards:
            synced_card = self._sync_card_record(card)
            if synced_card.vector_status == "synced":
                synced += 1
            else:
                failed += 1
        self.session.commit()
        return {
            "total": len(cards),
            "synced": synced,
            "failed": failed,
        }
