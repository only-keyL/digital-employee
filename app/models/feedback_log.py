"""用户反馈 ORM 模型（表 feedback_log）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class FeedbackLog(Base):
    """用户对问答结果的反馈记录。"""

    __tablename__ = "feedback_log"
    __table_args__ = (
        Index("idx_feedback_question_log_id", "question_log_id"),
        Index("idx_feedback_type", "feedback_type"),
        Index("idx_feedback_create_time", "create_time"),
        Index("idx_feedback_knowledge_card_id", "knowledge_card_id"),
        Index("idx_feedback_group_id", "group_id"),
        Index("idx_feedback_status", "status"),
        Index("idx_feedback_user_time", "user_id", "create_time"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    question_log_id: Mapped[int | None] = mapped_column(BigInteger)  # 关联问答日志 ID
    user_id: Mapped[str | None] = mapped_column(String(100))  # 反馈用户标识
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 反馈类型（如 useful/useless）
    comment: Mapped[str | None] = mapped_column(String(500))  # 可选文字备注
    knowledge_card_id: Mapped[int | None] = mapped_column(BigInteger)  # 关联知识卡片 ID
    group_id: Mapped[str | None] = mapped_column(String(128))  # 来源群 ID
    reason_type: Mapped[str | None] = mapped_column(String(64))  # 无用原因类型
    reason_text: Mapped[str | None] = mapped_column(Text)  # 用户填写的无用原因
    supplement_text: Mapped[str | None] = mapped_column(Text)  # 用户补充的正确答案或纠错内容
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")  # 反馈处理状态
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)  # 更新时间
