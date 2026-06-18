#!/usr/bin/env python
"""将 failed 且未达 max_retries 的向量任务重置为 pending（不直接执行 Qdrant 同步）。"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.config.settings import get_settings
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.vector_sync_task import VectorSyncTask

DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重试 failed 向量同步任务")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--limit", type=int, default=20, help="最多处理任务数")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写数据库")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)
    settings = get_settings()
    max_batch = min(args.limit, settings.ops_max_retry_tasks)

    session = SessionLocal()
    try:
        tasks = session.scalars(
            select(VectorSyncTask)
            .where(VectorSyncTask.status == "failed")
            .where(VectorSyncTask.retry_count < VectorSyncTask.max_retries)
            .order_by(VectorSyncTask.updated_at.asc())
            .limit(max_batch)
        ).all()

        print("=" * 60)
        print(f"failed 向量任务重试（dry_run={args.dry_run} limit={max_batch}）")
        print("=" * 60)

        if not tasks:
            print("无可重试任务")
            print("[PASS] 完成")
            return 0

        for task in tasks:
            print(
                f"  task_id={task.id} knowledge_id={task.knowledge_id} "
                f"retry={task.retry_count}/{task.max_retries}"
            )
            if not args.dry_run:
                task.status = "pending"
                task.error_message = None
                task.next_retry_at = datetime.now()
                task.updated_at = datetime.now()

        if args.dry_run:
            print(f"[DRY-RUN] 将重置 {len(tasks)} 条任务为 pending（未写库）")
        else:
            session.commit()
            print(f"[PASS] 已重置 {len(tasks)} 条任务为 pending")

        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 重试任务失败：{exc}")
        raise SystemExit(1) from exc
