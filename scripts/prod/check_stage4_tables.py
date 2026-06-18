#!/usr/bin/env python
"""Stage4 数据库表检查。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

from app.config.settings import get_settings
from app.core.settings import apply_env_file
from app.db.database import engine

STAGE4_TABLES = ("knowledge_contribution",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage4 表检查")
    parser.add_argument("--env-file", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)
    settings = get_settings()
    print("Stage4 表检查开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    ok = True
    for name in STAGE4_TABLES:
        if name in existing:
            print(f"  [OK] {name}")
        else:
            print(f"  [MISSING] {name}")
            ok = False
    if ok:
        print("[PASS] Stage4 表检查通过")
        return 0
    print("[FAIL] 缺少 Stage4 表")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Stage4 表检查异常：{exc}")
        raise SystemExit(1) from exc
