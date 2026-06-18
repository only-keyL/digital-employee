#!/usr/bin/env python
"""批量入队向量同步任务。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.database import SessionLocal
from app.services.stage3_vector_sync_service import Stage3VectorSyncService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="向量同步任务入队")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all-approved", action="store_true", help="入队全部 approved+enabled 知识")
    group.add_argument("--status", default="pending", help="按 vector_status 筛选（预留）")
    parser.add_argument(
        "--force-resync",
        action="store_true",
        help="忽略 vector_status=synced，强制重新入队（用于迁移到远程 Qdrant）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with SessionLocal() as session:
        service = Stage3VectorSyncService(session)
        if args.all_approved or args.status:
            count = service.enqueue_all_approved(force_resync=args.force_resync)
            session.commit()
            print(f"已入队 {count} 条向量同步任务")
            print("[PASS] 入队完成")
            return 0
    print("[FAIL] 未指定入队方式")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] 入队失败：{exc}")
        raise SystemExit(1) from exc
