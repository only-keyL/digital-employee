"""知识卡片修订建议 ORM 模型（表 knowledge_card_revision）。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KnowledgeCardRevision(Base):
    """知识卡片修订建议 ORM 模型。

    用于承接用户补充/纠错反馈生成的知识修订单。
    本表不直接影响正式知识卡片，只有审核通过后才会更新 knowledge_card。
    """

    __tablename__ = "knowledge_card_revision"
    __table_args__ = (
        Index("idx_revision_source_feedback_id", "source_feedback_id"),
        Index("idx_revision_original_card_id", "original_card_id"),
        Index("idx_revision_status", "status"),
        Index("idx_revision_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    source_feedback_id: Mapped[int | None] = mapped_column(BigInteger)  # 来源反馈 ID
    original_card_id: Mapped[int | None] = mapped_column(BigInteger)  # 被修订的原知识卡片 ID
    revision_type: Mapped[str] = mapped_column(String(64), nullable=False, default="update_existing")  # 修订类型
    proposed_title: Mapped[str | None] = mapped_column(String(255))  # 建议标题
    proposed_question: Mapped[str | None] = mapped_column(Text)  # 建议标准问题
    proposed_answer: Mapped[str | None] = mapped_column(Text)  # 建议标准答案
    proposed_solution: Mapped[str | None] = mapped_column(Text)  # 建议解决方案
    proposed_steps: Mapped[str | None] = mapped_column(Text)  # 建议排查步骤
    proposed_risk_notice: Mapped[str | None] = mapped_column(Text)  # 建议风险提醒
    similarity_result_json: Mapped[str | None] = mapped_column(Text)  # 重复检测相似度结果 JSON
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")  # 修订状态
    submit_user: Mapped[str | None] = mapped_column(String(128))  # 提交人
    audit_user: Mapped[str | None] = mapped_column(String(128))  # 审核人
    audit_time: Mapped[datetime | None] = mapped_column(DateTime)  # 审核时间
    audit_remark: Mapped[str | None] = mapped_column(Text)  # 审核备注
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )  # 更新时间
