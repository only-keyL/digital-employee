"""文档知识库数据访问层。"""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource
from app.repositories.base_repository import BaseRepository


class DocumentRepository(BaseRepository[DocumentSource]):
    """document_source / document_chunk 表查询与持久化。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, DocumentSource)

    def get_by_id(self, doc_id: int) -> DocumentSource | None:
        stmt = select(DocumentSource).where(DocumentSource.id == doc_id)
        return self.session.scalars(stmt).first()

    def get_active_by_id(self, doc_id: int) -> DocumentSource | None:
        stmt = select(DocumentSource).where(
            DocumentSource.id == doc_id,
            DocumentSource.deleted == 0,
        )
        return self.session.scalars(stmt).first()

    def get_by_file_hash(self, file_hash: str) -> DocumentSource | None:
        """按文件 hash 查重，避免重复上传生成多条记录。"""
        stmt = select(DocumentSource).where(
            DocumentSource.file_hash == file_hash,
            DocumentSource.deleted == 0,
        )
        return self.session.scalars(stmt).first()

    def list_documents(self, *, offset: int = 0, limit: int = 50) -> list[DocumentSource]:
        stmt = (
            select(DocumentSource)
            .where(DocumentSource.deleted == 0)
            .order_by(DocumentSource.create_time.desc())
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_documents(self) -> int:
        stmt = select(DocumentSource).where(DocumentSource.deleted == 0)
        return self.count(stmt)

    def add(self, doc: DocumentSource) -> DocumentSource:
        self.session.add(doc)
        self.session.flush()
        return doc

    def save(self) -> None:
        self.session.commit()

    def refresh(self, doc: DocumentSource) -> DocumentSource:
        self.session.refresh(doc)
        return doc

    def list_chunks_by_doc_id(
        self,
        doc_id: int,
        *,
        offset: int = 0,
        limit: int = 200,
        include_deleted: bool = False,
    ) -> list[DocumentChunk]:
        stmt = select(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
        if not include_deleted:
            stmt = stmt.where(DocumentChunk.deleted == 0)
        stmt = stmt.order_by(DocumentChunk.chunk_index.asc()).offset(offset).limit(limit)
        return list(self.session.scalars(stmt).all())

    def count_chunks_by_doc_id(self, doc_id: int, *, include_deleted: bool = False) -> int:
        stmt = select(DocumentChunk).where(DocumentChunk.doc_id == doc_id)
        if not include_deleted:
            stmt = stmt.where(DocumentChunk.deleted == 0)
        return self.count(stmt)

    def soft_delete_chunks_by_doc_id(self, doc_id: int) -> int:
        """重新切片前，将旧 chunk 逻辑删除，保留历史可追溯。"""
        result = self.session.execute(
            update(DocumentChunk)
            .where(DocumentChunk.doc_id == doc_id, DocumentChunk.deleted == 0)
            .values(deleted=1)
        )
        self.session.flush()
        return int(result.rowcount or 0)

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        self.session.add_all(chunks)
        self.session.flush()

    def get_chunk_by_id(self, chunk_id: int) -> DocumentChunk | None:
        stmt = select(DocumentChunk).where(DocumentChunk.id == chunk_id)
        return self.session.scalars(stmt).first()

    def get_syncable_chunk_by_id(self, chunk_id: int) -> DocumentChunk | None:
        """查询可参与检索/同步的切片（启用、未删除，且所属文档已解析启用）。"""
        stmt = (
            select(DocumentChunk)
            .join(DocumentSource, DocumentSource.id == DocumentChunk.doc_id)
            .where(
                DocumentChunk.id == chunk_id,
                DocumentChunk.deleted == 0,
                DocumentChunk.enabled == 1,
                DocumentSource.deleted == 0,
                DocumentSource.enabled == 1,
                DocumentSource.parse_status == "parsed",
            )
        )
        return self.session.scalars(stmt).first()

    def list_syncable_chunks_by_doc_id(self, doc_id: int) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .join(DocumentSource, DocumentSource.id == DocumentChunk.doc_id)
            .where(
                DocumentChunk.doc_id == doc_id,
                DocumentChunk.deleted == 0,
                DocumentChunk.enabled == 1,
                DocumentSource.deleted == 0,
                DocumentSource.enabled == 1,
                DocumentSource.parse_status == "parsed",
            )
            .order_by(DocumentChunk.chunk_index.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_all_syncable_chunks(self) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .join(DocumentSource, DocumentSource.id == DocumentChunk.doc_id)
            .where(
                DocumentChunk.deleted == 0,
                DocumentChunk.enabled == 1,
                DocumentSource.deleted == 0,
                DocumentSource.enabled == 1,
                DocumentSource.parse_status == "parsed",
            )
            .order_by(DocumentChunk.doc_id.asc(), DocumentChunk.chunk_index.asc())
        )
        return list(self.session.scalars(stmt).all())
