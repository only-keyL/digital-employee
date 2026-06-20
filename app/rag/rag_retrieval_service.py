"""Stage3 RAG 检索服务：embedding + Qdrant + MySQL 回查（知识卡片 + 文档切片）。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.models.knowledge_card import KnowledgeCard
from app.rag.confidence import classify_confidence
from app.rag.qdrant_vector_store import QdrantVectorStore, get_qdrant_vector_store
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)


@dataclass
class RagContextItem:
    source_type: str  # knowledge_card / document_chunk
    title: str
    score: float
    rank: int
    confidence_level: str
    content_text: str
    knowledge_id: int | None = None
    chunk_id: int | None = None
    doc_id: int | None = None
    doc_name: str | None = None
    section_path: str | None = None
    page_no: int | None = None
    card: KnowledgeCard | None = None
    chunk: DocumentChunk | None = None
    doc: DocumentSource | None = None


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
    answer_source: str | None = None


class RagRetrievalService:
    """对用户问题做 embedding 检索，并回查 MySQL 构建 LLM 上下文。"""

    MAX_KNOWLEDGE_SOURCES = 3
    MAX_DOCUMENT_SOURCES = 3

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
        self.knowledge_repo = KnowledgeRepository(session)
        self.document_repo = DocumentRepository(session)
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

        knowledge_contexts, document_contexts = self._build_contexts(raw_hits)
        contexts = knowledge_contexts[: self.MAX_KNOWLEDGE_SOURCES] + document_contexts[: self.MAX_DOCUMENT_SOURCES]
        top_score = float(raw_hits[0]["score"])
        top_level = classify_confidence(top_score, self.settings)
        matched = top_level in {"high", "medium"}
        answer_source = self._resolve_answer_source(knowledge_contexts, document_contexts, matched)

        if top_level == "low":
            return RagRetrievalResult(
                matched=False,
                confidence_level="low",
                top_score=top_score,
                contexts=contexts,
                raw_hits=raw_hits,
                fallback_reason="retrieval_score_below_threshold",
                latency_ms=int((time.perf_counter() - started) * 1000),
                answer_source=answer_source,
            )

        return RagRetrievalResult(
            matched=matched,
            confidence_level=top_level,
            top_score=top_score,
            contexts=contexts,
            raw_hits=raw_hits,
            latency_ms=int((time.perf_counter() - started) * 1000),
            answer_source=answer_source,
        )

    def _build_contexts(self, raw_hits: list[dict]) -> tuple[list[RagContextItem], list[RagContextItem]]:
        knowledge: list[RagContextItem] = []
        documents: list[RagContextItem] = []
        for hit in raw_hits:
            payload = hit.get("payload") or {}
            source_type = str(hit.get("source_type") or payload.get("source_type") or "")
            if not source_type:
                source_type = "document_chunk" if payload.get("chunk_id") else "knowledge_card"
            score = float(hit.get("score") or 0.0)
            rank = int(hit.get("rank") or 0)
            level = classify_confidence(score, self.settings)

            if source_type == "document_chunk":
                chunk_id = hit.get("chunk_id") or payload.get("chunk_id")
                if chunk_id is None:
                    continue
                chunk = self.document_repo.get_syncable_chunk_by_id(int(chunk_id))
                if chunk is None:
                    continue
                doc = self.document_repo.get_active_by_id(chunk.doc_id)
                if doc is None:
                    continue
                documents.append(
                    RagContextItem(
                        source_type="document_chunk",
                        title=str(payload.get("doc_name") or chunk.section_title or doc.doc_name),
                        score=score,
                        rank=rank,
                        confidence_level=level,
                        content_text=self._build_document_context_text(chunk, doc),
                        chunk_id=chunk.id,
                        doc_id=doc.id,
                        doc_name=doc.doc_name,
                        section_path=chunk.section_path,
                        page_no=chunk.page_no,
                        chunk=chunk,
                        doc=doc,
                    )
                )
                continue

            knowledge_id = hit.get("knowledge_id") or payload.get("knowledge_id") or payload.get("card_id")
            if knowledge_id is None:
                continue
            card = self.knowledge_repo.get_searchable_by_id(int(knowledge_id))
            if card is None:
                continue
            knowledge.append(
                RagContextItem(
                    source_type="knowledge_card",
                    title=card.title,
                    score=score,
                    rank=rank,
                    confidence_level=level,
                    content_text=self._build_knowledge_context_text(card),
                    knowledge_id=card.id,
                    card=card,
                )
            )
        return knowledge, documents

    @staticmethod
    def _build_knowledge_context_text(card: KnowledgeCard) -> str:
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
    def _build_document_context_text(chunk: DocumentChunk, doc: DocumentSource) -> str:
        lines = [
            "【文档来源】",
            f"文档：《{doc.doc_name}》",
            f"章节：{chunk.section_path or chunk.section_title or '-'}",
        ]
        if chunk.page_no:
            lines.append(f"页码：{chunk.page_no}")
        lines.extend(["内容：", chunk.content or ""])
        return "\n".join(lines)

    @staticmethod
    def _resolve_answer_source(
        knowledge_contexts: list[RagContextItem],
        document_contexts: list[RagContextItem],
        matched: bool,
    ) -> str | None:
        if not matched:
            return None
        has_knowledge = bool(knowledge_contexts)
        has_document = bool(document_contexts)
        if has_knowledge and has_document:
            return "mixed"
        if has_document:
            return "document_chunk"
        if has_knowledge:
            return "knowledge_card"
        return None

    @staticmethod
    def payload_snapshot(hit: dict) -> str:
        """生成 retrieval_log 用的脱敏 payload 快照。"""
        payload = dict(hit.get("payload") or {})
        if "question_preview" in payload:
            payload["question_preview"] = sanitize_text(str(payload["question_preview"]), max_length=80)
        if "content" in payload:
            payload.pop("content", None)
        return json.dumps(payload, ensure_ascii=False)
