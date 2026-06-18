#!/usr/bin/env python
"""Stage6 表结构检查：message_process_log、admin_operation_log。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

from app.core.settings import apply_env_file
from app.db.database import engine
from app.models.admin_operation_log import AdminOperationLog
from app.models.message_process_log import MessageProcessLog

DEFAULT_ENV_FILE = "docs/prod/.env"
REQUIRED_TABLES = {
    "message_process_log": {
        "source",
        "message_id",
        "content_hash",
        "status",
        "response_json",
    },
    "admin_operation_log": {
        "operation_id",
        "operator",
        "action",
        "target_type",
        "target_id",
        "before_snapshot_json",
        "after_snapshot_json",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage6 表结构检查")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    failed = 0

    print("=" * 60)
    print("Stage6 表结构检查")
    print("=" * 60)

    for table, required_cols in REQUIRED_TABLES.items():
        if table not in existing:
            print(f"[FAIL] 缺少表 {table}")
            failed += 1
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        missing = required_cols - cols
        if missing:
            print(f"[FAIL] 表 {table} 缺少字段：{', '.join(sorted(missing))}")
            failed += 1
        else:
            print(f"[PASS] 表 {table} 字段齐全")

    # ORM 映射可导入
    _ = MessageProcessLog.__tablename__, AdminOperationLog.__tablename__
    print(f"[PASS] ORM 映射正常")

    print("-" * 60)
    if failed:
        print(f"[结果] 失败：{failed} 项未通过")
        return 1
    print("[结果] 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
