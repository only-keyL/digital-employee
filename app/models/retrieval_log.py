"""Stage3 检索日志 ORM（表 retrieval_log）。"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class RetrievalLog(Base):
    """Qdrant TopK 检索结果明细。"""

    __tablename__ = "retrieval_log"
    __table_args__ = (
        Index("idx_retrieval_log_run_id", "run_id"),
        Index("idx_retrieval_log_knowledge_id", "knowledge_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    payload_snapshot: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
