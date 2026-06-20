"""文档来源 ORM 模型（表 document_source）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class DocumentSource(Base):
    """上传文档主信息：文件元数据、解析状态与切片统计。"""

    __tablename__ = "document_source"
    __table_args__ = (
        Index("idx_doc_file_hash", "file_hash"),
        Index("idx_doc_parse_status", "parse_status"),
        Index("idx_doc_system_module", "system_name", "module_name"),
        Index("idx_doc_deleted", "deleted"),
        Index("idx_doc_enabled", "enabled"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    file_ext: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    system_name: Mapped[str | None] = mapped_column(String(100))
    module_name: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[str | None] = mapped_column(String(50))
    parse_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
