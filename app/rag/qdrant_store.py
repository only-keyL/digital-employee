"""Qdrant local store for knowledge card vectors."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config.settings import settings
from app.models.knowledge_card import KnowledgeCard
from app.rag.embedding_service import EmbeddingService, get_embedding_service
from app.services.knowledge_content import build_knowledge_content_text, card_to_content_dict


class QdrantStoreError(Exception):
    pass


class QdrantDimensionMismatchError(QdrantStoreError):
    pass


@dataclass
class QdrantSearchHit:
    card_id: int
    title: str
    score: float
    payload: dict[str, Any]


class QdrantStore:
    def __init__(
        self,
        *,
        embedding_service: EmbeddingService | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        self._embedding = embedding_service or get_embedding_service()
        self._client = client or self._create_client()
        self._collection = settings.qdrant_collection
        self._distance = self._resolve_distance(settings.qdrant_distance)

    @staticmethod
    def _create_client() -> QdrantClient:
        if settings.qdrant_mode.lower() != "local":
            raise QdrantStoreError(f"阶段五仅支持 QDRANT_MODE=local，当前为: {settings.qdrant_mode}")
        return QdrantClient(path=settings.qdrant_local_path)

    @staticmethod
    def _resolve_distance(distance: str) -> qmodels.Distance:
        mapping = {
            "COSINE": qmodels.Distance.COSINE,
            "EUCLID": qmodels.Distance.EUCLID,
            "DOT": qmodels.Distance.DOT,
        }
        key = distance.upper()
        if key not in mapping:
            raise QdrantStoreError(f"不支持的 QDRANT_DISTANCE: {distance}")
        return mapping[key]

    def get_collection_vector_size(self) -> int | None:
        if not self._client.collection_exists(self._collection):
            return None
        info = self._client.get_collection(self._collection)
        params = info.config.params
        if params and params.vectors:
            if isinstance(params.vectors, qmodels.VectorParams):
                return params.vectors.size
        return None

    def init_collection(self, *, recreate: bool = False) -> None:
        vector_size = self._embedding.get_dimension()
        exists = self._client.collection_exists(self._collection)

        if recreate and exists:
            self._client.delete_collection(self._collection)
            exists = False

        if exists:
            current_size = self.get_collection_vector_size()
            if current_size is not None and current_size != vector_size:
                raise QdrantDimensionMismatchError(
                    f"Qdrant collection '{self._collection}' vector_size={current_size}, "
                    f"but embedding dimension={vector_size}. "
                    "请执行: python scripts/rebuild_qdrant.py --recreate"
                )
            return

        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=self._distance),
        )

    def build_payload(self, card: KnowledgeCard) -> dict[str, Any]:
        return {
            "card_id": card.id,
            "title": card.title,
            "question": card.question or "",
            "system_name": card.system_name or "",
            "module_name": card.module_name or "",
            "tags": card.tags or "",
            "audit_status": card.audit_status,
            "enabled": card.enabled,
            "version": card.version,
            "content_hash": card.content_hash or "",
        }

    def upsert_knowledge_card(self, card: KnowledgeCard) -> None:
        self.init_collection()
        content = build_knowledge_content_text(card_to_content_dict(card))
        vector = self._embedding.embed_text(content)
        point = qmodels.PointStruct(
            id=card.id,
            vector=vector,
            payload=self.build_payload(card),
        )
        self._client.upsert(collection_name=self._collection, points=[point])

    def delete_knowledge_card(self, card_id: int) -> None:
        if not self._client.collection_exists(self._collection):
            return
        self._client.delete(
            collection_name=self._collection,
            points_selector=qmodels.PointIdsList(points=[card_id]),
        )

    def search(self, query_text: str, *, top_k: int | None = None) -> list[QdrantSearchHit]:
        if not self._client.collection_exists(self._collection):
            return []

        limit = top_k or settings.top_k
        vector = self._embedding.embed_text(query_text)
        results = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=limit,
            with_payload=True,
        )
        hits: list[QdrantSearchHit] = []
        for point in results.points:
            payload = point.payload or {}
            card_id = int(payload.get("card_id", point.id))
            hits.append(
                QdrantSearchHit(
                    card_id=card_id,
                    title=str(payload.get("title", "")),
                    score=float(point.score or 0.0),
                    payload=payload,
                )
            )
        return hits

    def rebuild_from_mysql(self, cards: list[KnowledgeCard]) -> tuple[int, int]:
        self.init_collection(recreate=False)
        success = 0
        failed = 0
        for card in cards:
            try:
                self.upsert_knowledge_card(card)
                success += 1
            except Exception:
                failed += 1
        return success, failed

    def health_check(self) -> bool:
        try:
            collections = self._client.get_collections()
            return any(item.name == self._collection for item in collections.collections)
        except Exception:
            return False

    def count_points(self) -> int:
        if not self._client.collection_exists(self._collection):
            return 0
        info = self._client.get_collection(self._collection)
        return int(info.points_count or 0)


@lru_cache
def get_qdrant_store() -> QdrantStore:
    return QdrantStore()
