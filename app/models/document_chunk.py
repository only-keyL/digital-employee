"""文档切片 ORM 模型（表 document_chunk）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DocumentChunk(Base):
    """文档切片：章节路径、正文与向量同步预留字段。"""

    __tablename__ = "document_chunk"
    __table_args__ = (
        Index("idx_chunk_doc_id", "doc_id"),
        Index("idx_chunk_vector_status", "vector_status"),
        Index("idx_chunk_deleted", "deleted"),
        Index("idx_chunk_doc_index", "doc_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    doc_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section_title: Mapped[str | None] = mapped_column(String(500))
    section_path: Mapped[str | None] = mapped_column(String(1000))
    page_no: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    vector_id: Mapped[str | None] = mapped_column(String(100))
    vector_error: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
