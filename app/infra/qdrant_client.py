"""Qdrant 远程基础设施客户端：连通性检查与固定测试向量读写。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config.settings import Settings
from app.core.desensitize import mask_url

logger = logging.getLogger(__name__)

# 本阶段固定测试点 UUID，避免污染真实知识数据
_INFRA_TEST_POINT_ID = UUID("00000000-0000-4000-8000-000000000001")
_INFRA_TEST_VECTOR = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
_INFRA_TEST_PAYLOAD = {
    "source": "stage2_infra_check",
    "text": "基础设施连通性测试",
}


class QdrantInfraError(Exception):
    """Qdrant 基础设施操作失败。"""


class QdrantInfraClient:
    """Qdrant 远程客户端：只做基础设施连通性，不接入 RAG 主链路。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: QdrantClient | None = None

    def _ensure_remote_configured(self) -> None:
        """远程模式必须配置 URL；local 模式本客户端不支持。"""
        if self._settings.qdrant_mode.lower() != "remote":
            raise QdrantInfraError(
                f"基础设施 Qdrant 检查要求 QDRANT_MODE=remote，当前为：{self._settings.qdrant_mode}"
            )
        if not self._settings.qdrant_url.strip():
            raise QdrantInfraError("未配置 QDRANT_URL，无法连接远程 Qdrant。")

    def _get_client(self) -> QdrantClient:
        """懒创建 QdrantClient，避免 import 时连接。"""
        self._ensure_remote_configured()
        if self._client is None:
            try:
                kwargs: dict[str, Any] = {
                    "url": self._settings.qdrant_url,
                    "timeout": self._settings.qdrant_timeout_seconds,
                }
                if self._settings.qdrant_api_key.strip():
                    kwargs["api_key"] = self._settings.qdrant_api_key
                self._client = QdrantClient(**kwargs)
            except Exception as exc:
                logger.error(
                    "Qdrant 连接初始化失败，URL=%s，原因=%s",
                    mask_url(self._settings.qdrant_url),
                    exc,
                )
                raise QdrantInfraError(f"Qdrant 连接初始化失败：{exc}") from exc
        return self._client

    def is_write_allowed(self, allow_write: bool) -> bool:
        """是否允许写入测试向量：必须显式传入 allow_write=True。"""
        return allow_write

    def check_write_guard(self, allow_write: bool) -> None:
        """未显式授权时禁止写入；prod / _prod collection 额外给出中文提示。"""
        if allow_write:
            return
        if self._settings.is_prod:
            raise QdrantInfraError(
                "APP_ENV=prod 时禁止默认写入测试向量，请显式传入 --allow-qdrant-write。"
            )
        collection = self._settings.qdrant_collection.lower()
        if collection.endswith("_prod"):
            raise QdrantInfraError(
                "QDRANT_COLLECTION 为生产集合，禁止默认写入测试向量，请显式传入 --allow-qdrant-write。"
            )
        raise QdrantInfraError("写入 Qdrant 测试向量需要显式传入 --allow-qdrant-write。")

    def check_connection(self) -> bool:
        """检查远程 Qdrant 连接是否可用。"""
        client = self._get_client()
        try:
            client.get_collections()
            return True
        except Exception as exc:
            logger.error(
                "Qdrant 连接检查失败，URL=%s，原因=%s",
                mask_url(self._settings.qdrant_url),
                exc,
            )
            raise QdrantInfraError(f"Qdrant 连接检查失败：{exc}") from exc

    def ensure_collection(self, vector_size: int = 8) -> None:
        """确保 collection 存在，不存在则创建（仅基础设施测试用）。"""
        client = self._get_client()
        collection = self._settings.qdrant_collection
        try:
            if client.collection_exists(collection):
                return
            client.create_collection(
                collection_name=collection,
                vectors_config=qmodels.VectorParams(
                    size=vector_size,
                    distance=qmodels.Distance.COSINE,
                ),
            )
        except Exception as exc:
            logger.error("Qdrant 创建 collection 失败，collection=%s，原因=%s", collection, exc)
            raise QdrantInfraError(f"Qdrant 创建 collection 失败：{exc}") from exc

    def upsert_test_point(self, allow_write: bool = False) -> str:
        """写入固定测试向量，仅用于基础设施验收。"""
        self.check_write_guard(allow_write)
        if not self.is_write_allowed(allow_write):
            raise QdrantInfraError("当前不允许写入 Qdrant 测试向量。")

        self.ensure_collection(vector_size=len(_INFRA_TEST_VECTOR))
        client = self._get_client()
        point_id = _INFRA_TEST_POINT_ID
        try:
            client.upsert(
                collection_name=self._settings.qdrant_collection,
                points=[
                    qmodels.PointStruct(
                        id=point_id,
                        vector=_INFRA_TEST_VECTOR,
                        payload=_INFRA_TEST_PAYLOAD,
                    )
                ],
            )
            return str(point_id)
        except Exception as exc:
            logger.error("Qdrant 写入测试向量失败，原因=%s", exc)
            raise QdrantInfraError(f"Qdrant 写入测试向量失败：{exc}") from exc

    def search_test_point(self) -> list[dict[str, Any]]:
        """检索测试向量，验证 query 能力。"""
        client = self._get_client()
        try:
            results = client.query_points(
                collection_name=self._settings.qdrant_collection,
                query=_INFRA_TEST_VECTOR,
                limit=3,
                with_payload=True,
            )
            return [
                {
                    "id": str(point.id),
                    "score": float(point.score or 0.0),
                    "source": (point.payload or {}).get("source"),
                }
                for point in results.points
            ]
        except Exception as exc:
            logger.error("Qdrant 检索测试向量失败，原因=%s", exc)
            raise QdrantInfraError(f"Qdrant 检索测试向量失败：{exc}") from exc

    def safe_info(self) -> dict[str, Any]:
        """返回脱敏后的 Qdrant 配置信息。"""
        url = self._settings.qdrant_url
        masked_url = mask_url(url) if url else ""
        if masked_url and "://" in masked_url:
            masked_url = masked_url.split("://", 1)[0] + "://***"
        return {
            "configured": bool(url.strip()),
            "mode": self._settings.qdrant_mode,
            "url": masked_url,
            "collection": self._settings.qdrant_collection,
        }
