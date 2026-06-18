"""Stage3 Embedding 客户端：真实向量生成，禁止伪造向量。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 8000


class EmbeddingClientError(Exception):
    """Embedding 调用失败。"""


class EmbeddingClient:
    """从 Settings 读取配置，调用真实 embedding 服务。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: AsyncOpenAI | None = None

    @property
    def vector_size(self) -> int:
        return self._settings.embedding_dimension

    def _validate_config(self) -> None:
        provider = self._settings.embedding_provider.lower()
        if provider == "disabled":
            raise EmbeddingClientError("EMBEDDING_PROVIDER=disabled，无法生成向量。")
        if provider == "mock":
            raise EmbeddingClientError("Stage3 RAG 禁止使用 mock embedding。")
        if not self._settings.embedding_model.strip():
            raise EmbeddingClientError("未配置 EMBEDDING_MODEL。")
        if provider == "openai_compatible" and not self._settings.embedding_api_key.strip():
            raise EmbeddingClientError("openai_compatible 模式必须配置 EMBEDDING_API_KEY。")

    def _prepare_text(self, text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            raise EmbeddingClientError("embedding 输入文本不能为空。")
        if len(cleaned) > _MAX_TEXT_LEN:
            cleaned = cleaned[:_MAX_TEXT_LEN]
        return cleaned

    def _validate_vector(self, vector: list[float]) -> list[float]:
        expected = self.vector_size
        if len(vector) != expected:
            raise EmbeddingClientError(
                f"Embedding 向量维度不一致：期望 {expected}，实际 {len(vector)}。"
            )
        return vector

    async def embed_text(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self._validate_config()
        prepared = [self._prepare_text(t) for t in texts]
        provider = self._settings.embedding_provider.lower()

        if provider in {"qdrant_fastembed", "fastembed"}:
            return await asyncio.to_thread(self._embed_fastembed_sync, prepared)
        if provider == "openai_compatible":
            return await self._embed_openai_compatible(prepared)
        raise EmbeddingClientError(f"不支持的 EMBEDDING_PROVIDER: {provider}")

    async def _embed_openai_compatible(self, texts: list[str]) -> list[list[float]]:
        client = self._get_openai_client()
        last_error: Exception | None = None
        for attempt in range(1, self._settings.embedding_max_retries + 2):
            try:
                response = await client.embeddings.create(
                    model=self._settings.embedding_model,
                    input=texts,
                )
                vectors = [self._validate_vector(item.embedding) for item in response.data]
                logger.info("Embedding 生成成功，batch=%d", len(texts))
                return vectors
            except Exception as exc:
                last_error = exc
                logger.warning("Embedding 调用失败（第 %d 次）：%s", attempt, exc)
                if attempt <= self._settings.embedding_max_retries:
                    await asyncio.sleep(0.5 * attempt)
        raise EmbeddingClientError(f"Embedding 调用失败：{last_error}") from last_error

    def _embed_fastembed_sync(self, texts: list[str]) -> list[list[float]]:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise EmbeddingClientError("未安装 fastembed，无法使用 qdrant_fastembed。") from exc
        model = TextEmbedding(model_name=self._settings.embedding_model)
        vectors = list(model.embed(texts))
        return [self._validate_vector(list(map(float, vec))) for vec in vectors]

    def _get_openai_client(self) -> AsyncOpenAI:
        if self._client is None:
            api_key = self._settings.embedding_api_key or "not-needed"
            self._client = AsyncOpenAI(
                api_key=api_key,
                base_url=self._settings.embedding_base_url or None,
                timeout=float(self._settings.embedding_timeout_seconds),
                max_retries=self._settings.embedding_max_retries,
            )
        return self._client

    def safe_info(self) -> dict[str, Any]:
        return {
            "provider": self._settings.embedding_provider,
            "model": self._settings.embedding_model,
            "vector_size": self.vector_size,
            "configured": self._settings.embedding_provider.lower() != "disabled",
        }
