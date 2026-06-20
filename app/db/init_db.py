"""初始化数据库表结构与 system_config 默认值。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401 — register models with Base.metadata
    AskRun,
    DocumentChunk,
    DocumentSource,
    FeedbackLog,
    KnowledgeContribution,
    KnowledgeCard,
    LlmCallLog,
    QuestionLog,
    RetrievalLog,
    SystemConfig,
    Tag,
    UnansweredQuestion,
    VectorSyncTask,
)
from app.repositories.system_config_repository import SystemConfigRepository


def init_database() -> None:
    """创建全部 ORM 表并 upsert system_config 默认配置。"""
    print(f"Connecting to: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    Base.metadata.create_all(bind=engine)
    print("Tables created (or already exist).")

    with SessionLocal() as session:
        repo = SystemConfigRepository(session)
        inserted = repo.upsert_defaults()
        session.commit()
        print(f"System config defaults upserted: {inserted} item(s).")

    table_names = sorted(Base.metadata.tables.keys())
    print(f"Total tables: {len(table_names)}")
    for name in table_names:
        print(f"  - {name}")


if __name__ == "__main__":
    try:
        init_database()
        print("[PASS] Database initialization completed.")
    except Exception as exc:
        print(f"[FAIL] Database initialization failed: {exc}")
        sys.exit(1)
