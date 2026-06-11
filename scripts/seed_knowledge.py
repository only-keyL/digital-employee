"""Idempotent seed script for demo knowledge cards."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.database import SessionLocal
from app.services.knowledge_service import KnowledgeService
from app.services.seed_data import SEED_KNOWLEDGE_CARDS


def main() -> int:
    inserted = 0
    skipped = 0
    with SessionLocal() as session:
        service = KnowledgeService(session)
        for item in SEED_KNOWLEDGE_CARDS:
            card = service.create_seed_card(item)
            if card is None:
                skipped += 1
                print(f"[SKIP] Already exists: {item['title']}")
            else:
                inserted += 1
                print(f"[INSERT] {item['title']} (id={card.id})")
        session.commit()
    print(f"[DONE] inserted={inserted}, skipped={skipped}, total_definitions={len(SEED_KNOWLEDGE_CARDS)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FAIL] Seed import failed: {exc}")
        sys.exit(1)
