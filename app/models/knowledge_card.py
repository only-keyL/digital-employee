"""知识卡片 ORM 模型（表 knowledge_card）。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class KnowledgeCard(Base):
    """知识库主数据：问答内容、审核与向量同步状态。"""

    __tablename__ = "knowledge_card"
    __table_args__ = (
        Index("idx_knowledge_audit_enabled", "audit_status", "enabled"),
        Index("idx_knowledge_vector_status", "vector_status"),
        Index("idx_knowledge_deleted", "deleted"),
        Index("idx_knowledge_system_module", "system_name", "module_name"),
        Index("idx_knowledge_need_review", "need_review"),
        Index("idx_knowledge_quality_score", "quality_score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")  # 标题
    question: Mapped[str | None] = mapped_column(Text)  # 标准问题
    answer: Mapped[str | None] = mapped_column(Text)  # 标准答案
    system_name: Mapped[str | None] = mapped_column(String(100))  # 所属系统
    module_name: Mapped[str | None] = mapped_column(String(100))  # 所属模块
    tags: Mapped[str | None] = mapped_column(String(500))  # 标签
    scene: Mapped[str | None] = mapped_column(String(500))  # 场景描述
    reason_analysis: Mapped[str | None] = mapped_column(Text)  # 原因分析
    troubleshooting_steps: Mapped[str | None] = mapped_column(Text)  # 排查步骤
    solution: Mapped[str | None] = mapped_column(Text)  # 解决方案
    risk_notice: Mapped[str | None] = mapped_column(Text)  # 风险提醒
    source_group: Mapped[str | None] = mapped_column(String(100))  # 来源群
    source_user: Mapped[str | None] = mapped_column(String(100))  # 来源用户
    audit_status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")  # 审核状态
    audit_user: Mapped[str | None] = mapped_column(String(100))  # 审核人
    audit_time: Mapped[datetime | None] = mapped_column(DateTime)  # 审核时间
    audit_remark: Mapped[str | None] = mapped_column(String(500))  # 审核备注
    vector_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 向量状态
    vector_id: Mapped[str | None] = mapped_column(String(100))  # Qdrant point ID
    vector_error: Mapped[str | None] = mapped_column(Text)  # 向量同步错误
    content_hash: Mapped[str | None] = mapped_column(String(64))  # 内容哈希
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # 版本号
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 是否启用
    deleted: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 逻辑删除
    useful_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 有用反馈次数
    useless_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 无用反馈次数
    supplement_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 补充/纠错反馈次数
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))  # 知识卡片质量分
    need_review: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)  # 是否需要复核 0/1
    last_feedback_time: Mapped[datetime | None] = mapped_column(DateTime)  # 最近一次反馈时间
    create_user: Mapped[str | None] = mapped_column(String(100))  # 创建人
    update_user: Mapped[str | None] = mapped_column(String(100))  # 更新人
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
