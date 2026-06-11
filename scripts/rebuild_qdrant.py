"""Rebuild Qdrant vectors from MySQL knowledge cards."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.database import SessionLocal
from app.rag.embedding_service import get_embedding_service
from app.rag.qdrant_store import QdrantDimensionMismatchError
from app.services.vector_sync_service import VectorSyncService


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild Qdrant knowledge card vectors from MySQL")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate collection before full upsert",
    )
    args = parser.parse_args()

    embedding = get_embedding_service()
    print(f"[INFO] Embedding provider: {embedding.provider_name} ({embedding.get_dimension()} dim)")

    try:
        with SessionLocal() as session:
            service = VectorSyncService(session)
            if args.recreate:
                print("[INFO] Recreate mode: rebuilding collection from scratch")
                stats = service.rebuild_all(recreate=True)
            else:
                try:
                    service.qdrant.init_collection(recreate=False)
                except QdrantDimensionMismatchError as exc:
                    print(f"[FAIL] {exc}")
                    return 1
                stats = service.rebuild_all(recreate=False)
    except Exception as exc:
        print(f"[FAIL] Rebuild failed: {exc}")
        return 1

    print(
        f"[INFO] Rebuild complete: total={stats['total']}, "
        f"synced={stats['synced']}, failed={stats['failed']}"
    )
    if stats["failed"] > 0:
        print("[FAIL] Some knowledge cards failed to sync.")
        return 1

    print("[PASS] Rebuild Qdrant OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
