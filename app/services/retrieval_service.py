"""向量检索编排（/api/ask 的 RAG 检索层）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.knowledge_card import KnowledgeCard
from app.rag.confidence import classify_confidence
from app.rag.embedding_service import EmbeddingService, get_embedding_service
from app.rag.qdrant_store import QdrantSearchHit, QdrantStore, get_qdrant_store
from app.repositories.knowledge_repository import KnowledgeRepository


@dataclass
class RetrievalHit:
    """单条检索命中结果（含 MySQL 卡片实体）。"""

    card: KnowledgeCard  # 知识卡片 ORM
    title: str  # 卡片标题
    score: float  # 相似度分数


@dataclass
class RetrievalResult:
    """RetrievalService.retrieve 的返回结构。"""

    matched: bool  # 是否达到阈值命中（high / medium）
    confidence_level: str  # 置信度等级：high / medium / low / none
    similarity_score: float  # 最高相似度
    best_hit: RetrievalHit | None = None  # 最佳命中
    hits: list[RetrievalHit] = field(default_factory=list)  # 有效 hit 列表
    fallback_reason: str | None = None  # 未命中原因
    error: str | None = None  # 检索异常信息


class RetrievalService:
    """协调 Qdrant 检索与 MySQL 卡片校验。"""

    MAX_SOURCES = 3  # 最多返回来源条数

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
        self.threshold = settings.similarity_threshold  # 命中阈值，默认 0.75
        self.top_k = settings.top_k  # Qdrant top_k，默认 5

    def retrieve(self, question: str) -> RetrievalResult:
        """对问题做向量检索，并按阈值判定是否命中。"""
        try:
            raw_hits = self.qdrant.search(question, top_k=self.top_k)
        except Exception as exc:
            return RetrievalResult(
                matched=False,
                confidence_level="none",
                similarity_score=0.0,
                fallback_reason="向量检索异常",
                error=str(exc),
            )

        if not raw_hits:
            return RetrievalResult(
                matched=False,
                confidence_level="low",
                similarity_score=0.0,
                fallback_reason="向量检索未命中",
            )

        valid_hits = self._validate_hits(raw_hits)
        best_score = raw_hits[0].score
        if not valid_hits:
            return RetrievalResult(
                matched=False,
                confidence_level="low",
                similarity_score=best_score,
                fallback_reason="向量检索未命中",
            )

        best_hit = valid_hits[0]
        confidence_level = classify_confidence(best_hit.score)
        # 高 / 中置信度才进入生成答案分支，低置信度不强答
        matched = confidence_level in {"high", "medium"}
        if not matched:
            return RetrievalResult(
                matched=False,
                confidence_level=confidence_level,
                similarity_score=best_hit.score,
                best_hit=best_hit,
                hits=valid_hits[: self.MAX_SOURCES],
                fallback_reason="相似度低于阈值",
            )

        return RetrievalResult(
            matched=True,
            confidence_level=confidence_level,
            similarity_score=best_hit.score,
            best_hit=best_hit,
            hits=valid_hits[: self.MAX_SOURCES],
        )

    def _validate_hits(self, raw_hits: list[QdrantSearchHit]) -> list[RetrievalHit]:
        """回查 MySQL，过滤 deleted / 未 approved / 未 enabled 的卡片。"""
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
