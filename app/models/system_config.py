from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SystemConfig(Base):
    """系统键值配置表。"""

    __tablename__ = "system_config"
    __table_args__ = (Index("uk_config_key", "config_key", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)  # 主键
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)  # 配置键（唯一）
    config_value: Mapped[str | None] = mapped_column(Text)  # 配置值
    description: Mapped[str | None] = mapped_column(String(500))  # 配置说明
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())  # 创建时间
    update_time: Mapped[datetime] = mapped_column(  # 最后更新时间
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
