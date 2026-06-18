#!/usr/bin/env python
"""执行向量同步 worker。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.services.stage3_vector_sync_service import Stage3VectorSyncService

DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="向量同步 worker")
    parser.add_argument("--limit", type=int, default=20, help="单次处理任务数")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="环境配置文件")
    parser.add_argument("--dry-run", action="store_true", help="仅统计，不写入 Qdrant")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env_path = Path(args.env_file)
    if not env_path.is_file():
        print(f"[FAIL] 配置文件不存在：{env_path}")
        return 2

    apply_env_file(str(env_path))
    print(f"向量同步 worker 启动 limit={args.limit} dry_run={args.dry_run}")

    async def _run() -> dict[str, int]:
        with SessionLocal() as session:
            service = Stage3VectorSyncService(session)
            return await service.process_pending(limit=args.limit, dry_run=args.dry_run)

    stats = asyncio.run(_run())
    print(
        "执行结果："
        f" total={stats.get('total', 0)}"
        f" success={stats.get('success', 0)}"
        f" failed={stats.get('failed', 0)}"
        f" skipped={stats.get('skipped', 0)}"
    )
    if stats.get("failed", 0) > 0:
        print("[WARN] 存在失败任务，请检查 vector_sync_task.error_message")
        return 1
    print("[PASS] worker 执行完成")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] worker 异常：{exc}")
        raise SystemExit(1) from exc
