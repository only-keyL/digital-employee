#!/usr/bin/env python
"""Stage4 数据库表初始化：knowledge_contribution。"""

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
from app.models import KnowledgeContribution  # noqa: F401

STAGE4_TABLES = ("knowledge_contribution",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage4 表初始化")
    parser.add_argument("--env-file", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)
    settings = get_settings()
    print("Stage4 表初始化开始")
    print(f"数据库：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables[name] for name in STAGE4_TABLES])
    for name in STAGE4_TABLES:
        print(f"  - {name}")
    print("[PASS] Stage4 表初始化成功")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[FAIL] Stage4 表初始化失败：{exc}")
        raise SystemExit(1) from exc
