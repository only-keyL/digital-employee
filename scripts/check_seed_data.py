"""演示种子数据验收脚本（阶段三）。

检查 knowledge_card 表中是否存在足够的 approved+enabled 演示数据。
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import SessionLocal
from app.models.knowledge_card import KnowledgeCard


def main() -> int:
    """检查演示种子数据是否就绪，返回进程退出码。"""
    print(f"Checking seed data in: {settings.mysql_database}")
    with SessionLocal() as session:
        total = session.scalar(
            select(func.count()).select_from(KnowledgeCard).where(KnowledgeCard.deleted == 0)
        ) or 0
        approved_enabled = session.scalar(
            select(func.count())
            .select_from(KnowledgeCard)
            .where(
                KnowledgeCard.deleted == 0,
                KnowledgeCard.audit_status == "approved",
                KnowledgeCard.enabled == 1,
            )
        ) or 0

    if total == 0:
        print("[FAIL] knowledge_card has no demo data.")
        print("       Run: python scripts/seed_knowledge.py")
        return 1

    if approved_enabled < 5:
        print(
            f"[FAIL] approved + enabled knowledge cards expected >= 5, got {approved_enabled} "
            f"(total active cards={total})."
        )
        return 1

    print(f"[PASS] Seed data OK: total_active={total}, approved_enabled={approved_enabled}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FAIL] Seed check failed: {exc}")
        sys.exit(1)
