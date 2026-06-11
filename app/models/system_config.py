from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class SystemConfig(Base):
    __tablename__ = "system_config"
    __table_args__ = (Index("uk_config_key", "config_key", unique=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    config_key: Mapped[str] = mapped_column(String(100), nullable=False)
    config_value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(String(500))
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
