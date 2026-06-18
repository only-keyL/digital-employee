"""知识重复检测记录 ORM 模型（表 knowledge_duplicate_check_log）。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KnowledgeDuplicateCheckLog(Base):
    """知识重复检测记录 ORM 模型。

    用于记录知识卡片创建、更新、沉淀、补充反馈等场景下的重复检测过程与结果。
    本阶段仅建表与基础查询，不实现重复检测业务流程。
    """

    __tablename__ = "knowledge_duplicate_check_log"
    __table_args__ = (
        Index("idx_duplicate_source_card_id", "source_card_id"),
        Index("idx_duplicate_candidate_card_id", "candidate_card_id"),
        Index("idx_duplicate_check_level", "check_level"),
        Index("idx_duplicate_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    source_card_id: Mapped[int | None] = mapped_column(BigInteger)  # 待检测知识卡片 ID
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)  # 检测来源
    candidate_card_id: Mapped[int | None] = mapped_column(BigInteger)  # 疑似重复的候选卡片 ID
    similarity_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))  # 相似度
    check_level: Mapped[str] = mapped_column(String(32), nullable=False, default="none")  # 重复等级
    check_result: Mapped[str] = mapped_column(String(32), nullable=False, default="none")  # 检测结果
    operator_user: Mapped[str | None] = mapped_column(String(128))  # 操作人
    decision: Mapped[str | None] = mapped_column(String(64))  # 后续处理决策
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
