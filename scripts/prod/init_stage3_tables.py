#!/usr/bin/env python
"""Stage3 数据库表初始化：仅创建缺失表，不修改已有表结构。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import get_settings
from app.core.settings import apply_env_file
from app.db.database import Base, engine
from app.models import (  # noqa: F401
    AskRun,
    FeedbackLog,
    KnowledgeCard,
    LlmCallLog,
    QuestionLog,
    RetrievalLog,
    SystemConfig,
    Tag,
    UnansweredQuestion,
    VectorSyncTask,
)

STAGE3_TABLES = ("ask_run", "retrieval_log", "llm_call_log", "vector_sync_task")
DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage3 表初始化")
    parser.add_argument("--env-file", default=None, help="可选：指定 env 文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)
    settings = get_settings()
    print("Stage3 表初始化开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    existing = set(Base.metadata.tables.keys())
    missing = [name for name in STAGE3_TABLES if name not in existing]
    if missing:
        print(f"待注册模型缺失：{missing}")
        return 1

    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables[name] for name in STAGE3_TABLES])
    print("Stage3 表创建完成（已存在则跳过）：")
    for name in STAGE3_TABLES:
        print(f"  - {name}")
    print("[PASS] Stage3 表初始化成功")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Stage3 表初始化失败：{exc}")
        raise SystemExit(1) from exc
