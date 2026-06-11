from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Tag(Base):
    __tablename__ = "tag"
    __table_args__ = (
        Index("idx_tag_name", "tag_name"),
        Index("idx_tag_type", "tag_type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tag_type: Mapped[str] = mapped_column(String(50), nullable=False, default="custom")
    enabled: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
