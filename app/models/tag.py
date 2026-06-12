from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Tag(Base):
    """知识标签字典表。"""

    __tablename__ = "tag"
    __table_args__ = (
        Index("idx_tag_name", "tag_name"),
        Index("idx_tag_type", "tag_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 标签名称
    tag_type: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")  # 标签类型
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)  # 是否启用（1/0）
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
