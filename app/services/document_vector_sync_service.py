"""文档切片向量同步：复用 Embedding 与 Qdrant 基础设施。"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.rag.document_vector_payload_builder import (
    build_document_chunk_payload,
    build_document_chunk_vector_text,
    is_sync_eligible_chunk,
    qdrant_point_id_for_chunk,
    vector_id_for_chunk,
)
from app.rag.qdrant_store import QdrantStore, get_qdrant_store
from app.rag.qdrant_vector_store import QdrantVectorStore, get_qdrant_vector_store
from app.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class DocumentVectorSyncService:
    """文档 chunk 向量同步：写入与知识卡片共用的 Qdrant collection。"""

    def __init__(
        self,
        session: Session,
        *,
        embedding_client: EmbeddingClient | None = None,
        qdrant_store: QdrantStore | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.repo = DocumentRepository(session)
        self.embedding = embedding_client or EmbeddingClient(self.settings)
        self.qdrant_store = qdrant_store or get_qdrant_store()
        self.vector_store = vector_store or get_qdrant_vector_store()

    def sync_document(self, doc_id: int) -> dict[str, int]:
        doc = self.repo.get_active_by_id(doc_id)
        if doc is None:
            raise ValueError("文档不存在")
        chunks = self.repo.list_syncable_chunks_by_doc_id(doc_id)
        synced = 0
        failed = 0
        for chunk in chunks:
            try:
                self._sync_chunk_record(chunk, doc)
                if chunk.vector_status == "synced":
                    synced += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                chunk.vector_status = "failed"
                chunk.vector_error = str(exc)[:2000]
                logger.exception("文档 chunk 同步失败 chunk_id=%s", chunk.id)
        self.session.commit()
        return {"total": len(chunks), "synced": synced, "failed": failed}

    def sync_chunk(self, chunk_id: int) -> DocumentChunk:
        chunk = self.repo.get_chunk_by_id(chunk_id)
        if chunk is None:
            raise ValueError("文档切片不存在")
        doc = self.repo.get_active_by_id(chunk.doc_id)
        if doc is None:
            raise ValueError("文档不存在")
        self._sync_chunk_record(chunk, doc)
        self.session.commit()
        self.session.refresh(chunk)
        return chunk

    def delete_document_vectors(self, doc_id: int, *, commit: bool = True) -> dict[str, int]:
        doc = self.repo.get_by_id(doc_id)
        if doc is None:
            raise ValueError("文档不存在")
        chunks = self.repo.list_chunks_by_doc_id(doc_id, include_deleted=True, limit=5000)
        deleted = 0
        for chunk in chunks:
            if chunk.vector_id or chunk.vector_status == "synced":
                self._delete_chunk_vector(chunk)
                deleted += 1
        if commit:
            self.session.commit()
        else:
            self.session.flush()
        return {"total": len(chunks), "deleted": deleted}

    def rebuild_all_documents(self, *, recreate: bool = False) -> dict[str, int]:
        if recreate:
            self.qdrant_store.init_collection(recreate=False)
        chunks = self.repo.list_all_syncable_chunks()
        doc_cache: dict[int, DocumentSource] = {}
        synced = 0
        failed = 0
        for chunk in chunks:
            doc = doc_cache.get(chunk.doc_id)
            if doc is None:
                doc = self.repo.get_active_by_id(chunk.doc_id)
                if doc is not None:
                    doc_cache[chunk.doc_id] = doc
            if doc is None or not is_sync_eligible_chunk(chunk, doc):
                continue
            try:
                self._sync_chunk_record(chunk, doc)
                if chunk.vector_status == "synced":
                    synced += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
        self.session.commit()
        return {"total": len(chunks), "synced": synced, "failed": failed}

    def _sync_chunk_record(self, chunk: DocumentChunk, doc: DocumentSource) -> None:
        if not is_sync_eligible_chunk(chunk, doc):
            self._delete_chunk_vector(chunk)
            chunk.vector_status = "pending"
            chunk.vector_id = None
            chunk.vector_error = None
            self.session.flush()
            return

        vector_text = build_document_chunk_vector_text(chunk, doc)
        payload = build_document_chunk_payload(chunk, doc)
        point_id = qdrant_point_id_for_chunk(chunk.id)

        try:
            vector = asyncio.run(self.embedding.embed_text(vector_text))
            self._upsert_to_stores(point_id, vector, payload, chunk, doc)
            chunk.vector_status = "synced"
            chunk.vector_id = vector_id_for_chunk(chunk.id)
            chunk.vector_error = None
        except (EmbeddingClientError, Exception) as exc:
            chunk.vector_status = "failed"
            chunk.vector_error = str(exc)[:2000]
        self.session.flush()

    def _upsert_to_stores(
        self,
        point_id: int,
        vector: list[float],
        payload: dict,
        chunk: DocumentChunk,
        doc: DocumentSource,
    ) -> None:
        """本地 QdrantStore（/api/ask）与远程 QdrantVectorStore（AskGraphV2）共用 payload。"""
        self.qdrant_store.upsert_document_chunk(point_id, vector, payload)
        try:
            self.vector_store.upsert_point(point_id, vector, payload)
        except Exception as exc:
            logger.warning("远程 Qdrant 同步文档 chunk 失败 chunk_id=%s: %s", chunk.id, exc)

    def _delete_chunk_vector(self, chunk: DocumentChunk) -> None:
        point_id = qdrant_point_id_for_chunk(chunk.id)
        try:
            self.qdrant_store.delete_document_chunk(point_id)
        except Exception as exc:
            logger.warning("删除本地文档向量失败 chunk_id=%s: %s", chunk.id, exc)
        try:
            self.vector_store.delete_point(point_id)
        except Exception as exc:
            logger.warning("删除远程文档向量失败 chunk_id=%s: %s", chunk.id, exc)
        chunk.vector_status = "pending"
        chunk.vector_id = None
        chunk.vector_error = None
