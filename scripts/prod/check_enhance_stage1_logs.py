#!/usr/bin/env python
"""生产 V1 增强阶段 1：数据与日志体系验收脚本。

检查新增字段、新表、索引及 Repository 基础查询能力。
不依赖大模型、Qdrant 或 uvicorn 服务。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

from app.core.settings import apply_env_file
from app.db.database import SessionLocal, engine
from app.models.feedback_log import FeedbackLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_card_revision import KnowledgeCardRevision
from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.models.question_log import QuestionLog
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.knowledge_card_revision_repository import KnowledgeCardRevisionRepository
from app.repositories.knowledge_duplicate_check_repository import KnowledgeDuplicateCheckRepository
from app.repositories.question_repository import QuestionRepository

DEFAULT_ENV_FILE = "docs/prod/.env"

QUESTION_LOG_COLUMNS = {
    "primary_matched_card_id",
    "primary_matched_card_title",
    "confidence_level",
    "answer_status",
    "answer_source",
    "system_name",
    "module_name",
    "used_context",
    "context_source",
}

FEEDBACK_LOG_COLUMNS = {
    "knowledge_card_id",
    "group_id",
    "reason_type",
    "reason_text",
    "supplement_text",
    "status",
    "updated_at",
}

KNOWLEDGE_CARD_COLUMNS = {
    "useful_count",
    "useless_count",
    "supplement_count",
    "quality_score",
    "need_review",
    "last_feedback_time",
}

REQUIRED_INDEXES = {
    "question_log": {
        "idx_question_primary_card_id",
        "idx_question_confidence_level",
        "idx_question_answer_status",
        "idx_question_system_module",
        "idx_question_user_group_time",
    },
    "feedback_log": {
        "idx_feedback_knowledge_card_id",
        "idx_feedback_group_id",
        "idx_feedback_status",
        "idx_feedback_user_time",
    },
    "knowledge_card": {
        "idx_knowledge_need_review",
        "idx_knowledge_quality_score",
    },
    "knowledge_card_revision": {
        "idx_revision_source_feedback_id",
        "idx_revision_original_card_id",
        "idx_revision_status",
        "idx_revision_created_at",
    },
    "knowledge_duplicate_check_log": {
        "idx_duplicate_source_card_id",
        "idx_duplicate_candidate_card_id",
        "idx_duplicate_check_level",
        "idx_duplicate_created_at",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段1 数据与日志体系验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="可选环境变量文件路径")
    return parser.parse_args()


def check_columns(inspector, table_name: str, required: set[str]) -> list[str]:
    """检查表字段是否齐全，返回缺失字段列表。"""
    if table_name not in inspector.get_table_names():
        return sorted(required)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    return sorted(required - existing)


def check_indexes(inspector, table_name: str, required: set[str]) -> list[str]:
    """检查表索引是否齐全，返回缺失索引列表。"""
    if table_name not in inspector.get_table_names():
        return sorted(required)
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    return sorted(required - existing)


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    failed_items: list[str] = []
    inspector = inspect(engine)

    print("=" * 60)
    print("增强阶段1 数据与日志体系验收")
    print("=" * 60)

    # 1. question_log 字段检查
    missing = check_columns(inspector, "question_log", QUESTION_LOG_COLUMNS)
    if missing:
        failed_items.append(f"question_log 缺少字段：{', '.join(missing)}")
        print(f"[FAIL] question_log 字段检查未通过：{', '.join(missing)}")
    else:
        print("[PASS] question_log 字段检查通过")

    # 2. feedback_log 字段检查
    missing = check_columns(inspector, "feedback_log", FEEDBACK_LOG_COLUMNS)
    if missing:
        failed_items.append(f"feedback_log 缺少字段：{', '.join(missing)}")
        print(f"[FAIL] feedback_log 字段检查未通过：{', '.join(missing)}")
    else:
        print("[PASS] feedback_log 字段检查通过")

    # 3. knowledge_card 字段检查
    missing = check_columns(inspector, "knowledge_card", KNOWLEDGE_CARD_COLUMNS)
    if missing:
        failed_items.append(f"knowledge_card 缺少字段：{', '.join(missing)}")
        print(f"[FAIL] knowledge_card 字段检查未通过：{', '.join(missing)}")
    else:
        print("[PASS] knowledge_card 字段检查通过")

    # 4. 新表存在性检查
    existing_tables = set(inspector.get_table_names())
    for table_name, label in (
        ("knowledge_card_revision", "knowledge_card_revision 表"),
        ("knowledge_duplicate_check_log", "knowledge_duplicate_check_log 表"),
    ):
        if table_name not in existing_tables:
            failed_items.append(f"缺少表 {table_name}")
            print(f"[FAIL] {label}检查未通过")
        else:
            print(f"[PASS] {label}检查通过")

    # 5. 索引检查
    index_failed = False
    for table_name, required_indexes in REQUIRED_INDEXES.items():
        missing_indexes = check_indexes(inspector, table_name, required_indexes)
        if missing_indexes:
            index_failed = True
            failed_items.append(f"{table_name} 缺少索引：{', '.join(missing_indexes)}")
    if index_failed:
        print("[FAIL] 索引检查未通过（详见失败项）")
    else:
        print("[PASS] 索引检查通过")

    # 6. ORM 导入检查
    try:
        _ = (
            QuestionLog.__tablename__,
            FeedbackLog.__tablename__,
            KnowledgeCard.__tablename__,
            KnowledgeCardRevision.__tablename__,
            KnowledgeDuplicateCheckLog.__tablename__,
        )
        print("[PASS] ORM 模型导入通过")
    except Exception as exc:
        failed_items.append(f"ORM 导入失败：{exc}")
        print(f"[FAIL] ORM 模型导入失败：{exc}")

    # 7. Repository 基础查询检查
    session = SessionLocal()
    try:
        question_repo = QuestionRepository(session)
        feedback_repo = FeedbackRepository(session)
        revision_repo = KnowledgeCardRevisionRepository(session)
        duplicate_repo = KnowledgeDuplicateCheckRepository(session)

        _ = question_repo.count_logs()
        _ = question_repo.list_user_recent_modules(user_id="__stage1_check__", group_id=None)
        _ = feedback_repo.count_by_status("new")
        _ = revision_repo.count_by_status("draft")
        _ = duplicate_repo.count_by_check_level("none")
        print("[PASS] Repository 基础查询通过")
    except Exception as exc:
        failed_items.append(f"Repository 查询失败：{exc}")
        print(f"[FAIL] Repository 基础查询失败：{exc}")
        print(f"失败原因：{exc}")
    finally:
        session.close()

    print("-" * 60)
    if failed_items:
        print(f"[FAIL] 失败项：{'; '.join(failed_items)}")
        for item in failed_items:
            print(f"失败原因：{item}")
        return 1

    print("[PASS] 阶段1日志底座验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
