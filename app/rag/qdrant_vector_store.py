"""Stage3 远程 Qdrant 向量存储（基于 Settings，复用 infra 连接逻辑）。"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config.settings import Settings, get_settings
from app.core.desensitize import mask_url
from app.rag.vector_store_base import VectorStore

logger = logging.getLogger(__name__)


class QdrantVectorStoreError(Exception):
    """Qdrant 向量存储异常。"""


class QdrantDimensionMismatchError(QdrantVectorStoreError):
    """Collection 维度与配置不一致，禁止自动删除重建。"""


class QdrantVectorStore(VectorStore):
    """远程 Qdrant 向量存储，point id 使用 knowledge_id。"""

    def __init__(self, settings: Settings | None = None, client: QdrantClient | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._collection = self._settings.effective_qdrant_rag_collection
        self._distance = self._resolve_distance(self._settings.qdrant_distance)

    def _get_client(self) -> QdrantClient:
        if self._client is not None:
            return self._client
        if self._settings.qdrant_mode.lower() != "remote":
            raise QdrantVectorStoreError(
                f"Stage3 RAG 要求 QDRANT_MODE=remote，当前为 {self._settings.qdrant_mode}"
            )
        if not self._settings.qdrant_url.strip():
            raise QdrantVectorStoreError("未配置 QDRANT_URL。")
        kwargs: dict[str, Any] = {
            "url": self._settings.qdrant_url,
            "timeout": self._settings.qdrant_timeout_seconds,
        }
        if self._settings.qdrant_api_key.strip():
            kwargs["api_key"] = self._settings.qdrant_api_key
        self._client = QdrantClient(**kwargs)
        return self._client

    @staticmethod
    def _resolve_distance(distance: str) -> qmodels.Distance:
        mapping = {
            "COSINE": qmodels.Distance.COSINE,
            "EUCLID": qmodels.Distance.EUCLID,
            "DOT": qmodels.Distance.DOT,
        }
        key = distance.upper()
        if key not in mapping:
            raise QdrantVectorStoreError(f"不支持的 QDRANT_DISTANCE: {distance}")
        return mapping[key]

    def get_collection_vector_size(self) -> int | None:
        client = self._get_client()
        if not client.collection_exists(self._collection):
            return None
        info = client.get_collection(self._collection)
        params = info.config.params
        if params and params.vectors and isinstance(params.vectors, qmodels.VectorParams):
            return params.vectors.size
        return None

    def ensure_collection(self, vector_size: int) -> None:
        """确保 collection 存在；已存在则校验维度，不一致直接失败。"""
        client = self._get_client()
        if client.collection_exists(self._collection):
            current = self.get_collection_vector_size()
            if current is not None and current != vector_size:
                raise QdrantDimensionMismatchError(
                    f"Qdrant collection '{self._collection}' 维度={current}，"
                    f"与 EMBEDDING_VECTOR_SIZE={vector_size} 不一致，请人工处理。"
                )
            return
        client.create_collection(
            collection_name=self._collection,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=self._distance),
        )
        logger.info("已创建 Qdrant collection=%s，维度=%d", self._collection, vector_size)

    def upsert_knowledge(self, knowledge_id: int, vector: list[float], payload: dict[str, Any]) -> None:
        self.ensure_collection(len(vector))
        client = self._get_client()
        client.upsert(
            collection_name=self._collection,
            points=[
                qmodels.PointStruct(id=knowledge_id, vector=vector, payload=payload),
            ],
        )

    def delete_knowledge(self, knowledge_id: int) -> None:
        client = self._get_client()
        if not client.collection_exists(self._collection):
            return
        client.delete(
            collection_name=self._collection,
            points_selector=qmodels.PointIdsList(points=[knowledge_id]),
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        client = self._get_client()
        if not client.collection_exists(self._collection):
            return []
        results = client.query_points(
            collection_name=self._collection,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            score_threshold=score_threshold,
        )
        hits: list[dict[str, Any]] = []
        for rank, point in enumerate(results.points, start=1):
            payload = point.payload or {}
            hits.append(
                {
                    "knowledge_id": int(payload.get("knowledge_id", point.id)),
                    "score": float(point.score or 0.0),
                    "rank": rank,
                    "payload": payload,
                    "collection_name": self._collection,
                }
            )
        return hits

    def count_points(self) -> int:
        client = self._get_client()
        if not client.collection_exists(self._collection):
            return 0
        info = client.get_collection(self._collection)
        return int(info.points_count or 0)


@lru_cache
def get_qdrant_vector_store() -> QdrantVectorStore:
    return QdrantVectorStore()
