"""未命中问题 ORM 模型（表 unanswered_question）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UnansweredQuestion(Base):
    """向量未命中问题的汇聚与沉淀状态（pending/converted/ignored）。"""

    __tablename__ = "unanswered_question"
    __table_args__ = (
        Index("idx_unanswered_status", "status"),
        Index("idx_unanswered_frequency", "frequency"),
        Index("idx_unanswered_last_seen", "last_seen_time"),
        Index("idx_unanswered_normalized_question", "normalized_question"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    question_log_id: Mapped[int | None] = mapped_column(BigInteger)  # 关联 question_log
    question: Mapped[str | None] = mapped_column(Text)  # 问题全文
    normalized_question: Mapped[str | None] = mapped_column(String(500))  # 归一化问题（去重键）
    summary: Mapped[str | None] = mapped_column(String(500))  # 摘要
    system_name: Mapped[str | None] = mapped_column(String(100))  # 系统名（convert 时可填）
    module_name: Mapped[str | None] = mapped_column(String(100))  # 模块名
    tags: Mapped[str | None] = mapped_column(String(500))  # 标签
    frequency: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 出现次数
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 沉淀状态
    convert_card_id: Mapped[int | None] = mapped_column(BigInteger)  # 转出后的知识卡片 ID
    last_seen_time: Mapped[datetime | None] = mapped_column(DateTime)  # 最近出现时间
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
