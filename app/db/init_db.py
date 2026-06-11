"""Initialize database tables and default system_config values."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import Base, SessionLocal, engine
from app.models import (  # noqa: F401 — register models with Base.metadata
    FeedbackLog,
    KnowledgeCard,
    QuestionLog,
    SystemConfig,
    Tag,
    UnansweredQuestion,
)
from app.repositories.system_config_repository import SystemConfigRepository


def init_database() -> None:
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
