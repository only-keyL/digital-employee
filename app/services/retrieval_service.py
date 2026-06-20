"""向量检索编排（/api/ask 的 RAG 检索层）。"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.models.knowledge_card import KnowledgeCard
from app.rag.confidence import classify_confidence
from app.rag.embedding_service import EmbeddingService, get_embedding_service
from app.rag.qdrant_store import QdrantSearchHit, QdrantStore, get_qdrant_store
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository


@dataclass
class RetrievalHit:
    """单条检索命中结果（知识卡片或文档切片）。"""

    source_type: str  # knowledge_card / document_chunk
    title: str
    score: float
    card: KnowledgeCard | None = None
    chunk: DocumentChunk | None = None
    doc: DocumentSource | None = None
    chunk_id: int | None = None
    doc_id: int | None = None
    doc_name: str | None = None
    section_path: str | None = None
    page_no: int | None = None


@dataclass
class RetrievalResult:
    """RetrievalService.retrieve 的返回结构。"""

    matched: bool
    confidence_level: str
    similarity_score: float
    best_hit: RetrievalHit | None = None
    hits: list[RetrievalHit] = field(default_factory=list)
    fallback_reason: str | None = None
    error: str | None = None
    answer_source: str | None = None


class RetrievalService:
    """协调 Qdrant 检索与 MySQL 回查（知识卡片 + 文档切片）。"""

    MAX_KNOWLEDGE_SOURCES = 3
    MAX_DOCUMENT_SOURCES = 3

    def __init__(
        self,
        session: Session,
        *,
        embedding_service: EmbeddingService | None = None,
        qdrant_store: QdrantStore | None = None,
    ) -> None:
        self.session = session
        self.knowledge_repo = KnowledgeRepository(session)
        self.document_repo = DocumentRepository(session)
        self.embedding = embedding_service or get_embedding_service()
        self.qdrant = qdrant_store or get_qdrant_store()
        self.top_k = settings.top_k

    def retrieve(self, question: str) -> RetrievalResult:
        """对问题做向量检索，知识卡片优先，文档切片作为补充。"""
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

        knowledge_hits, document_hits = self._validate_hits(raw_hits)
        merged_hits = knowledge_hits[: self.MAX_KNOWLEDGE_SOURCES] + document_hits[: self.MAX_DOCUMENT_SOURCES]
        top_score = raw_hits[0].score
        if not merged_hits:
            return RetrievalResult(
                matched=False,
                confidence_level="low",
                similarity_score=top_score,
                fallback_reason="向量检索未命中",
            )

        best_hit = merged_hits[0]
        confidence_level = classify_confidence(best_hit.score)
        matched = confidence_level in {"high", "medium"}
        answer_source = self._resolve_answer_source(knowledge_hits, document_hits, matched)

        if not matched:
            return RetrievalResult(
                matched=False,
                confidence_level=confidence_level,
                similarity_score=best_hit.score,
                best_hit=best_hit,
                hits=merged_hits,
                fallback_reason="相似度低于阈值",
                answer_source=answer_source,
            )

        return RetrievalResult(
            matched=True,
            confidence_level=confidence_level,
            similarity_score=best_hit.score,
            best_hit=best_hit,
            hits=merged_hits,
            answer_source=answer_source,
        )

    def _validate_hits(self, raw_hits: list[QdrantSearchHit]) -> tuple[list[RetrievalHit], list[RetrievalHit]]:
        """按 source_type 回查 MySQL，分别收集知识卡片与文档切片命中。"""
        knowledge: list[RetrievalHit] = []
        documents: list[RetrievalHit] = []
        for raw in raw_hits:
            if raw.source_type == "document_chunk" and raw.chunk_id is not None:
                chunk = self.document_repo.get_syncable_chunk_by_id(raw.chunk_id)
                if chunk is None:
                    continue
                doc = self.document_repo.get_active_by_id(chunk.doc_id)
                if doc is None:
                    continue
                documents.append(
                    RetrievalHit(
                        source_type="document_chunk",
                        title=raw.title or doc.doc_name,
                        score=raw.score,
                        chunk=chunk,
                        doc=doc,
                        chunk_id=chunk.id,
                        doc_id=doc.id,
                        doc_name=doc.doc_name,
                        section_path=chunk.section_path,
                        page_no=chunk.page_no,
                    )
                )
                continue

            card_id = raw.card_id
            if card_id is None:
                continue
            card = self.knowledge_repo.get_searchable_by_id(card_id)
            if card is None:
                continue
            knowledge.append(
                RetrievalHit(
                    source_type="knowledge_card",
                    title=card.title,
                    score=raw.score,
                    card=card,
                )
            )
        return knowledge, documents

    @staticmethod
    def _resolve_answer_source(
        knowledge_hits: list[RetrievalHit],
        document_hits: list[RetrievalHit],
        matched: bool,
    ) -> str | None:
        if not matched:
            return None
        has_knowledge = bool(knowledge_hits)
        has_document = bool(document_hits)
        if has_knowledge and has_document:
            return "mixed"
        if has_document:
            return "document_chunk"
        if has_knowledge:
            return "knowledge_card"
        return None
