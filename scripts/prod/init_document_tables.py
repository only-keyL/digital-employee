#!/usr/bin/env python
"""文档知识库阶段1：document_source / document_chunk 表初始化。"""

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
from sqlalchemy import text
from app.models import (  # noqa: F401
    DocumentChunk,
    DocumentSource,
)

DOCUMENT_STAGE1_TABLES = ("document_source", "document_chunk")
DEFAULT_ENV_FILE = ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="文档知识库阶段1 表初始化")
    parser.add_argument("--env-file", default=None, help="可选：指定 env 文件")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)
    settings = get_settings()
    print("文档知识库阶段1 表初始化开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")

    existing = set(Base.metadata.tables.keys())
    missing = [name for name in DOCUMENT_STAGE1_TABLES if name not in existing]
    if missing:
        print(f"待注册模型缺失：{missing}")
        return 1

    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables[name] for name in DOCUMENT_STAGE1_TABLES],
    )
    with engine.connect() as connection:
        result = connection.execute(
            text(
                """
                SELECT COUNT(*) AS cnt FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'document_chunk'
                  AND COLUMN_NAME = 'vector_error'
                """
            )
        )
        if int(result.scalar() or 0) == 0:
            connection.execute(text("ALTER TABLE document_chunk ADD COLUMN vector_error TEXT NULL"))
            connection.commit()
            print("  - 已补齐 document_chunk.vector_error 字段")
    print("文档知识库表创建完成（已存在则跳过）：")
    for name in DOCUMENT_STAGE1_TABLES:
        print(f"  - {name}")
    print("[PASS] 文档知识库阶段1 表初始化成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
