"""文档知识库业务编排：上传、解析、切片与状态流转。"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.repositories.document_repository import DocumentRepository
from app.schemas.document_schema import DocumentUploadMeta
from app.services.document_chunk_service import DocumentChunkService
from app.services.document_parse_service import DocumentParseError, DocumentParseService

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = frozenset({"txt", "md", "docx", "pdf"})


class DocumentServiceError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DocumentService:
    """文档上传、解析、切片与 CRUD 编排。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = DocumentRepository(session)
        self.parse_service = DocumentParseService()
        self.chunk_service = DocumentChunkService()

    @staticmethod
    def _compute_file_hash(content: bytes) -> str:
        """文件 hash 去重：相同内容不重复入库。"""
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _normalize_ext(filename: str) -> str:
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext not in ALLOWED_EXTENSIONS:
            allowed = "、".join(sorted(f".{item}" for item in ALLOWED_EXTENSIONS))
            raise DocumentServiceError(f"不支持的文件类型，仅允许：{allowed}")
        return ext

    def _upload_dir(self) -> Path:
        upload_dir = Path(settings.document_upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir

    def _max_upload_bytes(self) -> int:
        return settings.document_upload_max_size_mb * 1024 * 1024

    def _to_detail_dict(self, doc: DocumentSource) -> dict[str, Any]:
        return {
            "id": doc.id,
            "doc_name": doc.doc_name,
            "doc_type": doc.doc_type,
            "file_name": doc.file_name,
            "file_ext": doc.file_ext,
            "file_size": doc.file_size,
            "file_hash": doc.file_hash,
            "storage_path": doc.storage_path,
            "system_name": doc.system_name,
            "module_name": doc.module_name,
            "version": doc.version,
            "parse_status": doc.parse_status,
            "parse_error": doc.parse_error,
            "chunk_count": doc.chunk_count,
            "enabled": doc.enabled,
            "deleted": doc.deleted,
            "create_time": doc.create_time,
            "update_time": doc.update_time,
        }

    def _to_chunk_dict(self, chunk: DocumentChunk) -> dict[str, Any]:
        return {
            "id": chunk.id,
            "doc_id": chunk.doc_id,
            "doc_name": chunk.doc_name,
            "chunk_index": chunk.chunk_index,
            "section_title": chunk.section_title,
            "section_path": chunk.section_path,
            "page_no": chunk.page_no,
            "content": chunk.content,
            "content_hash": chunk.content_hash,
            "token_estimate": chunk.token_estimate,
            "vector_status": chunk.vector_status,
            "vector_id": chunk.vector_id,
            "vector_error": chunk.vector_error,
            "enabled": chunk.enabled,
            "create_time": chunk.create_time,
            "update_time": chunk.update_time,
        }

    def _get_active_or_raise(self, doc_id: int) -> DocumentSource:
        doc = self.repo.get_active_by_id(doc_id)
        if doc is None:
            raise DocumentServiceError("文档不存在")
        return doc

    def list_for_page(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        offset = (page - 1) * page_size
        items = self.repo.list_documents(offset=offset, limit=page_size)
        return {
            "items": [self._to_detail_dict(item) for item in items],
            "total": self.repo.count_documents(),
            "page": page,
            "page_size": page_size,
        }

    def list_api(self, *, page: int = 1, page_size: int = 20) -> dict[str, Any]:
        return self.list_for_page(page=page, page_size=page_size)

    def get_detail(self, doc_id: int) -> dict[str, Any]:
        return self._to_detail_dict(self._get_active_or_raise(doc_id))

    def list_chunks(self, doc_id: int, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        self._get_active_or_raise(doc_id)
        offset = (page - 1) * page_size
        chunks = self.repo.list_chunks_by_doc_id(doc_id, offset=offset, limit=page_size)
        return {
            "items": [self._to_chunk_dict(item) for item in chunks],
            "total": self.repo.count_chunks_by_doc_id(doc_id),
            "page": page,
            "page_size": page_size,
        }

    async def upload(self, file: UploadFile, meta: DocumentUploadMeta) -> dict[str, Any]:
        if not file.filename:
            raise DocumentServiceError("未选择上传文件")

        file_ext = self._normalize_ext(file.filename)
        content = await file.read()
        if not content:
            raise DocumentServiceError("上传文件为空")
        if len(content) > self._max_upload_bytes():
            raise DocumentServiceError(
                f"文件大小超过限制（最大 {settings.document_upload_max_size_mb}MB）"
            )

        file_hash = self._compute_file_hash(content)
        existing = self.repo.get_by_file_hash(file_hash)
        if existing is not None:
            return self._to_detail_dict(existing)

        safe_name = f"{uuid.uuid4().hex}.{file_ext}"
        storage_path = self._upload_dir() / safe_name
        storage_path.write_bytes(content)

        doc = DocumentSource(
            doc_name=meta.doc_name.strip(),
            doc_type=meta.doc_type,
            file_name=file.filename,
            file_ext=file_ext,
            file_size=len(content),
            file_hash=file_hash,
            storage_path=str(storage_path),
            system_name=(meta.system_name or "").strip() or None,
            module_name=(meta.module_name or "").strip() or None,
            version=(meta.version or "").strip() or None,
            parse_status="pending",
            chunk_count=0,
            enabled=1,
            deleted=0,
        )
        self.repo.add(doc)
        self.repo.save()
        self.repo.refresh(doc)

        return self._parse_and_persist_chunks(doc)

    def _parse_and_persist_chunks(self, doc: DocumentSource) -> dict[str, Any]:
        """parse_status 流转：pending -> parsed / failed。"""
        try:
            segments = self.parse_service.parse_file(doc.storage_path, doc.file_ext)
            drafts = self.chunk_service.build_chunks(
                segments,
                doc_name=doc.doc_name,
                system_name=doc.system_name,
                module_name=doc.module_name,
            )
            if not drafts:
                raise DocumentParseError("解析成功但未生成任何切片")

            self.repo.soft_delete_chunks_by_doc_id(doc.id)
            chunk_models = [
                DocumentChunk(
                    doc_id=doc.id,
                    doc_name=doc.doc_name,
                    chunk_index=draft.chunk_index,
                    section_title=draft.section_title,
                    section_path=draft.section_path,
                    page_no=draft.page_no,
                    content=draft.content,
                    content_hash=draft.content_hash,
                    token_estimate=draft.token_estimate,
                    vector_status="pending",
                    vector_id=None,
                    enabled=1,
                    deleted=0,
                )
                for draft in drafts
            ]
            self.repo.add_chunks(chunk_models)
            doc.parse_status = "parsed"
            doc.parse_error = None
            doc.chunk_count = len(chunk_models)
        except DocumentParseError as exc:
            doc.parse_status = "failed"
            doc.parse_error = exc.message
            doc.chunk_count = 0
            logger.warning("文档解析失败 doc_id=%s: %s", doc.id, exc.message)
        except Exception as exc:
            doc.parse_status = "failed"
            doc.parse_error = str(exc)
            doc.chunk_count = 0
            logger.exception("文档解析异常 doc_id=%s", doc.id)

        self.repo.save()
        self.repo.refresh(doc)
        return self._to_detail_dict(doc)

    def reparse(self, doc_id: int) -> dict[str, Any]:
        doc = self._get_active_or_raise(doc_id)
        doc.parse_status = "pending"
        doc.parse_error = None
        self.repo.save()
        return self._parse_and_persist_chunks(doc)

    def enable(self, doc_id: int) -> dict[str, Any]:
        doc = self._get_active_or_raise(doc_id)
        doc.enabled = 1
        self.repo.save()
        self.repo.refresh(doc)
        return self._to_detail_dict(doc)

    def disable(self, doc_id: int) -> dict[str, Any]:
        doc = self._get_active_or_raise(doc_id)
        doc.enabled = 0
        from app.services.document_vector_sync_service import DocumentVectorSyncService

        DocumentVectorSyncService(self.session).delete_document_vectors(doc_id, commit=False)
        self.repo.save()
        self.repo.refresh(doc)
        return self._to_detail_dict(doc)

    def delete(self, doc_id: int) -> dict[str, Any]:
        doc = self._get_active_or_raise(doc_id)
        from app.services.document_vector_sync_service import DocumentVectorSyncService

        DocumentVectorSyncService(self.session).delete_document_vectors(doc_id, commit=False)
        doc.deleted = 1
        doc.enabled = 0
        self.repo.soft_delete_chunks_by_doc_id(doc.id)
        self.repo.save()
        self.repo.refresh(doc)
        return self._to_detail_dict(doc)
