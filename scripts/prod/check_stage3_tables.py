#!/usr/bin/env python
"""Stage3 数据库表检查。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect

from app.config.settings import settings
from app.db.database import engine

STAGE3_TABLES = ("ask_run", "retrieval_log", "llm_call_log", "vector_sync_task")


def main() -> int:
    print("Stage3 表检查开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    ok = True
    for name in STAGE3_TABLES:
        if name in existing:
            print(f"  [OK] {name}")
        else:
            print(f"  [MISSING] {name}")
            ok = False
    if ok:
        print("[PASS] Stage3 表检查通过")
        return 0
    print("[FAIL] 缺少 Stage3 表，请先运行 init_stage3_tables.py")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Stage3 表检查异常：{exc}")
        raise SystemExit(1) from exc
