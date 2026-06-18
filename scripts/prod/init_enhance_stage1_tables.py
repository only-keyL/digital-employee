#!/usr/bin/env python
"""生产 V1 增强阶段 1：数据与日志体系表结构初始化。

幂等补齐 question_log / feedback_log / knowledge_card 字段与索引，
并创建 knowledge_card_revision、knowledge_duplicate_check_log 新表。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.config.settings import get_settings
from app.core.settings import apply_env_file
from app.db.database import Base, engine
from app.models import (  # noqa: F401
    FeedbackLog,
    KnowledgeCard,
    KnowledgeCardRevision,
    KnowledgeDuplicateCheckLog,
    QuestionLog,
)

# 本阶段新增表
ENHANCE_STAGE1_TABLES = (
    "knowledge_card_revision",
    "knowledge_duplicate_check_log",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段1 数据与日志体系表初始化")
    parser.add_argument("--env-file", default=None, help="可选环境变量文件路径")
    return parser.parse_args()


def column_exists(connection, table_name: str, column_name: str) -> bool:
    """判断指定字段是否已经存在，避免重复执行 ALTER TABLE。"""
    result = connection.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND COLUMN_NAME = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return int(result.scalar() or 0) > 0


def index_exists(connection, table_name: str, index_name: str) -> bool:
    """判断指定索引是否已经存在，避免重复执行 ALTER TABLE ADD INDEX。"""
    result = connection.execute(
        text(
            """
            SELECT COUNT(*) AS cnt
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table_name
              AND INDEX_NAME = :index_name
            """
        ),
        {"table_name": table_name, "index_name": index_name},
    )
    return int(result.scalar() or 0) > 0


def add_column_if_missing(
    connection,
    table_name: str,
    column_name: str,
    ddl: str,
) -> None:
    """字段不存在时才执行 ALTER TABLE ADD COLUMN。"""
    if column_exists(connection, table_name, column_name):
        print(f"  [跳过] {table_name}.{column_name} 已存在")
        return
    connection.execute(text(ddl))
    print(f"  [新增] {table_name}.{column_name}")


def add_index_if_missing(
    connection,
    table_name: str,
    index_name: str,
    ddl: str,
) -> None:
    """索引不存在时才执行 ALTER TABLE ADD INDEX。"""
    if index_exists(connection, table_name, index_name):
        print(f"  [跳过] 索引 {index_name} 已存在")
        return
    connection.execute(text(ddl))
    print(f"  [新增] 索引 {index_name}")


def upgrade_question_log(connection) -> None:
    """幂等补齐 question_log 增强字段与索引。"""
    print("补齐 question_log 字段...")
    columns = [
        (
            "primary_matched_card_id",
            "ALTER TABLE question_log ADD COLUMN primary_matched_card_id BIGINT NULL",
        ),
        (
            "primary_matched_card_title",
            "ALTER TABLE question_log ADD COLUMN primary_matched_card_title VARCHAR(255) NULL",
        ),
        (
            "confidence_level",
            "ALTER TABLE question_log ADD COLUMN confidence_level VARCHAR(16) NULL DEFAULT 'none'",
        ),
        (
            "answer_status",
            "ALTER TABLE question_log ADD COLUMN answer_status VARCHAR(32) NULL DEFAULT 'unknown'",
        ),
        (
            "answer_source",
            "ALTER TABLE question_log ADD COLUMN answer_source VARCHAR(64) NULL",
        ),
        (
            "system_name",
            "ALTER TABLE question_log ADD COLUMN system_name VARCHAR(100) NULL",
        ),
        (
            "module_name",
            "ALTER TABLE question_log ADD COLUMN module_name VARCHAR(100) NULL",
        ),
        (
            "used_context",
            "ALTER TABLE question_log ADD COLUMN used_context SMALLINT NOT NULL DEFAULT 0",
        ),
        (
            "context_source",
            "ALTER TABLE question_log ADD COLUMN context_source VARCHAR(64) NULL",
        ),
    ]
    for column_name, ddl in columns:
        add_column_if_missing(connection, "question_log", column_name, ddl)

    print("补齐 question_log 索引...")
    indexes = [
        (
            "idx_question_primary_card_id",
            "ALTER TABLE question_log ADD INDEX idx_question_primary_card_id (primary_matched_card_id)",
        ),
        (
            "idx_question_confidence_level",
            "ALTER TABLE question_log ADD INDEX idx_question_confidence_level (confidence_level)",
        ),
        (
            "idx_question_answer_status",
            "ALTER TABLE question_log ADD INDEX idx_question_answer_status (answer_status)",
        ),
        (
            "idx_question_system_module",
            "ALTER TABLE question_log ADD INDEX idx_question_system_module (system_name, module_name)",
        ),
        (
            "idx_question_user_group_time",
            "ALTER TABLE question_log ADD INDEX idx_question_user_group_time (user_id, group_id, create_time)",
        ),
    ]
    for index_name, ddl in indexes:
        add_index_if_missing(connection, "question_log", index_name, ddl)


def upgrade_feedback_log(connection) -> None:
    """幂等补齐 feedback_log 增强字段与索引。"""
    print("补齐 feedback_log 字段...")
    columns = [
        (
            "knowledge_card_id",
            "ALTER TABLE feedback_log ADD COLUMN knowledge_card_id BIGINT NULL",
        ),
        (
            "group_id",
            "ALTER TABLE feedback_log ADD COLUMN group_id VARCHAR(128) NULL",
        ),
        (
            "reason_type",
            "ALTER TABLE feedback_log ADD COLUMN reason_type VARCHAR(64) NULL",
        ),
        (
            "reason_text",
            "ALTER TABLE feedback_log ADD COLUMN reason_text TEXT NULL",
        ),
        (
            "supplement_text",
            "ALTER TABLE feedback_log ADD COLUMN supplement_text TEXT NULL",
        ),
        (
            "status",
            "ALTER TABLE feedback_log ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'new'",
        ),
        (
            "updated_at",
            "ALTER TABLE feedback_log ADD COLUMN updated_at DATETIME NULL",
        ),
    ]
    for column_name, ddl in columns:
        add_column_if_missing(connection, "feedback_log", column_name, ddl)

    print("补齐 feedback_log 索引...")
    indexes = [
        (
            "idx_feedback_knowledge_card_id",
            "ALTER TABLE feedback_log ADD INDEX idx_feedback_knowledge_card_id (knowledge_card_id)",
        ),
        (
            "idx_feedback_group_id",
            "ALTER TABLE feedback_log ADD INDEX idx_feedback_group_id (group_id)",
        ),
        (
            "idx_feedback_status",
            "ALTER TABLE feedback_log ADD INDEX idx_feedback_status (status)",
        ),
        (
            "idx_feedback_user_time",
            "ALTER TABLE feedback_log ADD INDEX idx_feedback_user_time (user_id, create_time)",
        ),
    ]
    for index_name, ddl in indexes:
        add_index_if_missing(connection, "feedback_log", index_name, ddl)


def upgrade_knowledge_card(connection) -> None:
    """幂等补齐 knowledge_card 增强字段与索引。"""
    print("补齐 knowledge_card 字段...")
    columns = [
        (
            "useful_count",
            "ALTER TABLE knowledge_card ADD COLUMN useful_count INT NOT NULL DEFAULT 0",
        ),
        (
            "useless_count",
            "ALTER TABLE knowledge_card ADD COLUMN useless_count INT NOT NULL DEFAULT 0",
        ),
        (
            "supplement_count",
            "ALTER TABLE knowledge_card ADD COLUMN supplement_count INT NOT NULL DEFAULT 0",
        ),
        (
            "quality_score",
            "ALTER TABLE knowledge_card ADD COLUMN quality_score DECIMAL(6,4) NULL",
        ),
        (
            "need_review",
            "ALTER TABLE knowledge_card ADD COLUMN need_review SMALLINT NOT NULL DEFAULT 0",
        ),
        (
            "last_feedback_time",
            "ALTER TABLE knowledge_card ADD COLUMN last_feedback_time DATETIME NULL",
        ),
    ]
    for column_name, ddl in columns:
        add_column_if_missing(connection, "knowledge_card", column_name, ddl)

    print("补齐 knowledge_card 索引...")
    indexes = [
        (
            "idx_knowledge_need_review",
            "ALTER TABLE knowledge_card ADD INDEX idx_knowledge_need_review (need_review)",
        ),
        (
            "idx_knowledge_quality_score",
            "ALTER TABLE knowledge_card ADD INDEX idx_knowledge_quality_score (quality_score)",
        ),
    ]
    for index_name, ddl in indexes:
        add_index_if_missing(connection, "knowledge_card", index_name, ddl)


def create_new_tables() -> None:
    """创建本阶段新增表（已存在则跳过）。"""
    print("创建新增表（如不存在）...")
    Base.metadata.create_all(
        bind=engine,
        tables=[Base.metadata.tables[name] for name in ENHANCE_STAGE1_TABLES],
    )
    for name in ENHANCE_STAGE1_TABLES:
        print(f"  - {name}")


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    settings = get_settings()
    print("增强阶段1 表初始化开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")

    # 先创建新表，再对已有表做字段/索引补齐
    create_new_tables()

    with engine.begin() as connection:
        upgrade_question_log(connection)
        upgrade_feedback_log(connection)
        upgrade_knowledge_card(connection)

    print("[PASS] 增强阶段1 表初始化成功")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 增强阶段1 表初始化失败：{exc}")
        raise SystemExit(1) from exc
