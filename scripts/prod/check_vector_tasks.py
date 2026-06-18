#!/usr/bin/env python
"""向量同步任务运维检查：统计状态、列出失败摘要、检测明显不一致。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select

from app.core.desensitize import sanitize_text
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.knowledge_card import KnowledgeCard
from app.models.vector_sync_task import VectorSyncTask

DEFAULT_ENV_FILE = "docs/prod/.env"
STATUSES = ("pending", "running", "success", "failed", "skipped")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="向量同步任务检查")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)
    session = SessionLocal()
    try:
        print("=" * 60)
        print("向量同步任务统计")
        print("=" * 60)

        total = session.scalar(select(func.count()).select_from(VectorSyncTask)) or 0
        print(f"任务总数：{total}")

        for status in STATUSES:
            count = session.scalar(
                select(func.count()).select_from(VectorSyncTask).where(VectorSyncTask.status == status)
            ) or 0
            print(f"  {status}: {count}")

        print("-" * 60)
        print("最近失败任务摘要（最多 10 条）")
        failed_tasks = session.scalars(
            select(VectorSyncTask)
            .where(VectorSyncTask.status == "failed")
            .order_by(VectorSyncTask.updated_at.desc())
            .limit(10)
        ).all()
        if not failed_tasks:
            print("  无 failed 任务")
        else:
            for task in failed_tasks:
                err = sanitize_text(task.error_message or "", max_length=80)
                print(
                    f"  task_id={task.id} knowledge_id={task.knowledge_id} "
                    f"retry={task.retry_count}/{task.max_retries} err={err or '-'}"
                )

        print("-" * 60)
        print("knowledge_card.vector_status 与 task.status 明显不一致检查")
        inconsistent = 0
        recent_success = session.scalars(
            select(VectorSyncTask)
            .where(VectorSyncTask.status == "success")
            .order_by(VectorSyncTask.updated_at.desc())
            .limit(20)
        ).all()
        for task in recent_success:
            card = session.get(KnowledgeCard, task.knowledge_id)
            if card is None:
                continue
            if card.vector_status not in {"synced", "pending"} and task.status == "success":
                inconsistent += 1
                print(
                    f"  [WARN] knowledge_id={card.id} vector_status={card.vector_status} "
                    f"但 task_id={task.id} 已为 success"
                )
        if inconsistent == 0:
            print("  未发现明显不一致（抽样 success 任务）")

        print("=" * 60)
        print("[PASS] 向量任务检查完成")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 向量任务检查失败：{exc}")
        raise SystemExit(1) from exc
