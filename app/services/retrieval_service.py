"""Vector retrieval orchestration for /api/ask."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.knowledge_card import KnowledgeCard
from app.rag.embedding_service import EmbeddingService, get_embedding_service
from app.rag.qdrant_store import QdrantSearchHit, QdrantStore, get_qdrant_store
from app.repositories.knowledge_repository import KnowledgeRepository


@dataclass
class RetrievalHit:
    card: KnowledgeCard
    title: str
    score: float


@dataclass
class RetrievalResult:
    matched: bool
    similarity_score: float
    best_hit: RetrievalHit | None = None
    hits: list[RetrievalHit] = field(default_factory=list)
    fallback_reason: str | None = None
    error: str | None = None


class RetrievalService:
    MAX_SOURCES = 3

    def __init__(
        self,
        session: Session,
        *,
        embedding_service: EmbeddingService | None = None,
        qdrant_store: QdrantStore | None = None,
    ) -> None:
        self.session = session
        self.repo = KnowledgeRepository(session)
        self.embedding = embedding_service or get_embedding_service()
        self.qdrant = qdrant_store or get_qdrant_store()
        self.threshold = settings.similarity_threshold
        self.top_k = settings.top_k

    def retrieve(self, question: str) -> RetrievalResult:
        try:
            raw_hits = self.qdrant.search(question, top_k=self.top_k)
        except Exception as exc:
            return RetrievalResult(
                matched=False,
                similarity_score=0.0,
                fallback_reason="向量检索异常",
                error=str(exc),
            )

        if not raw_hits:
            return RetrievalResult(
                matched=False,
                similarity_score=0.0,
                fallback_reason="向量检索未命中",
            )

        valid_hits = self._validate_hits(raw_hits)
        best_score = raw_hits[0].score
        if not valid_hits:
            return RetrievalResult(
                matched=False,
                similarity_score=best_score,
                fallback_reason="向量检索未命中",
            )

        best_hit = valid_hits[0]
        if best_hit.score < self.threshold:
            return RetrievalResult(
                matched=False,
                similarity_score=best_hit.score,
                best_hit=best_hit,
                hits=valid_hits[: self.MAX_SOURCES],
                fallback_reason="相似度低于阈值",
            )

        return RetrievalResult(
            matched=True,
            similarity_score=best_hit.score,
            best_hit=best_hit,
            hits=valid_hits[: self.MAX_SOURCES],
        )

    def _validate_hits(self, raw_hits: list[QdrantSearchHit]) -> list[RetrievalHit]:
        valid: list[RetrievalHit] = []
        for raw in raw_hits:
            card = self.repo.get_searchable_by_id(raw.card_id)
            if card is None:
                continue
            valid.append(
                RetrievalHit(
                    card=card,
                    title=card.title,
                    score=raw.score,
                )
            )
        return valid
