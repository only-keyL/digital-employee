"""RAG 向量检索验收脚本（阶段五）。

检查 Embedding、Qdrant 集合、TopK 检索及相似度阈值。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.db.database import SessionLocal
from app.rag.embedding_service import get_embedding_service
from app.rag.qdrant_store import get_qdrant_store
from app.repositories.knowledge_repository import KnowledgeRepository

# 用于向量检索的查询文本
QUERY_TEXT = "登录失败账号无权限"
# TopK 结果中应包含的目标卡片标题关键词
TARGET_TITLE_KEYWORD = "登录失败提示账号无权限处理办法"


def main() -> int:
    """执行 RAG 向量检索验收，返回进程退出码。"""
    if settings.embedding_provider.lower() != "fastembed":
        print(
            f"[WARN] check_rag.py expects EMBEDDING_PROVIDER=fastembed, "
            f"current={settings.embedding_provider}"
        )

    embedding = get_embedding_service()
    print(f"[INFO] Embedding provider: {embedding.provider_name} ({embedding.get_dimension()} dim)")

    qdrant = get_qdrant_store()
    if not qdrant.health_check():
        print("[FAIL] Qdrant collection does not exist. Run: python scripts/rebuild_qdrant.py --recreate")
        return 1
    print(f"[PASS] Qdrant collection exists: {settings.qdrant_collection}")

    with SessionLocal() as session:
        repo = KnowledgeRepository(session)
        approved_enabled = repo.count_approved_enabled()
        synced_count = repo.count_vector_synced()
        print(f"[INFO] approved+enabled cards: {approved_enabled}")
        print(f"[INFO] vector_status=synced cards: {synced_count}")

        if approved_enabled == 0:
            print("[FAIL] No approved+enabled knowledge cards found in MySQL.")
            return 1

        if qdrant.count_points() == 0:
            print("[FAIL] Qdrant collection has no vectors. Run: python scripts/rebuild_qdrant.py --recreate")
            return 1

    hits = qdrant.search(QUERY_TEXT, top_k=settings.top_k)
    if not hits:
        print("[FAIL] Qdrant search returned empty TopK.")
        return 1

    print("[INFO] TopK results:")
    target_found = False
    best_score = hits[0].score
    for hit in hits:
        print(f"       - card_id={hit.card_id}, title={hit.title}, score={hit.score:.4f}")
        if TARGET_TITLE_KEYWORD in hit.title:
            target_found = True

    if not target_found:
        print(f"[FAIL] Target card not found in TopK: {TARGET_TITLE_KEYWORD}")
        return 1

    if best_score < settings.similarity_threshold:
        print(
            f"[WARN] best_score={best_score:.4f} < SIMILARITY_THRESHOLD={settings.similarity_threshold}"
        )
    else:
        print(f"[PASS] best_score={best_score:.4f} >= SIMILARITY_THRESHOLD={settings.similarity_threshold}")

    print("[PASS] RAG check OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
