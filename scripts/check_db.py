"""数据库连接与表结构验收脚本（阶段二）。

验证 MySQL 连通性及核心业务表是否已创建。
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import engine

# 阶段二要求必须存在的核心业务表
EXPECTED_TABLES = {
    "feedback_log",
    "knowledge_card",
    "question_log",
    "system_config",
    "tag",
    "unanswered_question",
}


def main() -> int:
    """执行数据库连通性与表结构验收，返回进程退出码。"""
    print(f"Checking MySQL: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            print("[PASS] MySQL connection OK.")

            db_name = conn.execute(text("SELECT DATABASE()")).scalar()
            if not db_name:
                print("[FAIL] No database selected.")
                return 1
            print(f"[PASS] Database exists: {db_name}")

            inspector = inspect(conn)
            tables = set(inspector.get_table_names())
            missing = EXPECTED_TABLES - tables
            if missing:
                print(f"[FAIL] Missing tables: {sorted(missing)}")
                print(f"       Existing tables: {sorted(tables)}")
                return 1

            print(f"[PASS] Core tables found: {len(EXPECTED_TABLES)}")
            for table_name in sorted(EXPECTED_TABLES):
                print(f"       - {table_name}")
            return 0
    except SQLAlchemyError as exc:
        print(f"[FAIL] Database check failed: {exc}")
        print("       Ensure MySQL is running, database is created, and init_db.py has been executed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
