from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.app_debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)  # 线程内会话工厂


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话，结束时自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
