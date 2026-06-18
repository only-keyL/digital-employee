"""Stage3 RAG 检索服务：embedding + Qdrant + MySQL 回查。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.models.knowledge_card import KnowledgeCard
from app.rag.confidence import classify_confidence
from app.rag.qdrant_vector_store import QdrantVectorStore, get_qdrant_vector_store
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)


@dataclass
class RagContextItem:
    knowledge_id: int
    title: str
    score: float
    rank: int
    confidence_level: str
    card: KnowledgeCard
    content_text: str


@dataclass
class RagRetrievalResult:
    matched: bool
    confidence_level: str
    top_score: float
    contexts: list[RagContextItem] = field(default_factory=list)
    raw_hits: list[dict] = field(default_factory=list)
    fallback_reason: str | None = None
    error: str | None = None
    latency_ms: int = 0


class RagRetrievalService:
    """对用户问题做 embedding 检索，并回查 MySQL 构建 LLM 上下文。"""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repo = KnowledgeRepository(session)
        self.embedding = embedding_client or EmbeddingClient(self.settings)
        self.store = vector_store or get_qdrant_vector_store()
        self.top_k = self.settings.top_k

    async def retrieve(self, question: str) -> RagRetrievalResult:
        started = time.perf_counter()
        normalized = (question or "").strip()
        if not normalized:
            return RagRetrievalResult(
                matched=False,
                confidence_level="none",
                top_score=0.0,
                fallback_reason="empty_question",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        try:
            vector = await self.embedding.embed_text(normalized)
            raw_hits = self.store.search(vector, top_k=self.top_k, score_threshold=None)
        except (EmbeddingClientError, Exception) as exc:
            logger.error("RAG 检索失败：%s", exc)
            return RagRetrievalResult(
                matched=False,
                confidence_level="none",
                top_score=0.0,
                fallback_reason="retrieval_error",
                error=str(exc),
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        if not raw_hits:
            return RagRetrievalResult(
                matched=False,
                confidence_level="low",
                top_score=0.0,
                fallback_reason="retrieval_score_below_threshold",
                raw_hits=[],
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        contexts: list[RagContextItem] = []
        for hit in raw_hits:
            kid = int(hit["knowledge_id"])
            card = self.repo.get_searchable_by_id(kid)
            if card is None:
                continue
            level = classify_confidence(float(hit["score"]), self.settings)
            content_text = self._build_context_text(card)
            contexts.append(
                RagContextItem(
                    knowledge_id=kid,
                    title=card.title,
                    score=float(hit["score"]),
                    rank=int(hit["rank"]),
                    confidence_level=level,
                    card=card,
                    content_text=content_text,
                )
            )

        top_score = float(raw_hits[0]["score"])
        top_level = classify_confidence(top_score, self.settings)
        matched = top_level in {"high", "medium"}

        if top_level == "low":
            return RagRetrievalResult(
                matched=False,
                confidence_level="low",
                top_score=top_score,
                contexts=contexts,
                raw_hits=raw_hits,
                fallback_reason="retrieval_score_below_threshold",
                latency_ms=int((time.perf_counter() - started) * 1000),
            )

        return RagRetrievalResult(
            matched=matched,
            confidence_level=top_level,
            top_score=top_score,
            contexts=contexts,
            raw_hits=raw_hits,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    @staticmethod
    def _build_context_text(card: KnowledgeCard) -> str:
        """组装 LLM 上下文（来自 MySQL 完整知识，不写入 Qdrant payload）。"""
        parts = [
            f"标题：{card.title}",
            f"问题：{card.question or ''}",
            f"答案：{card.answer or ''}",
        ]
        if card.solution:
            parts.append(f"解决方案：{card.solution}")
        if card.risk_notice:
            parts.append(f"风险提示：{card.risk_notice}")
        return "\n".join(parts)

    @staticmethod
    def payload_snapshot(hit: dict) -> str:
        """生成 retrieval_log 用的脱敏 payload 快照。"""
        payload = dict(hit.get("payload") or {})
        if "question_preview" in payload:
            payload["question_preview"] = sanitize_text(str(payload["question_preview"]), max_length=80)
        return json.dumps(payload, ensure_ascii=False)
