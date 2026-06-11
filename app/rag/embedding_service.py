"""Embedding providers for knowledge card vectorization and retrieval."""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config.settings import settings

if TYPE_CHECKING:
    pass


class EmbeddingServiceError(Exception):
    pass


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def get_dimension(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError


def _normalize_vector(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0:
        return values
    return [value / norm for value in values]


def _stable_mock_vector(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    seed = int.from_bytes(digest[:8], "big")
    values: list[float] = []
    for index in range(dim):
        seed = (seed * 1103515245 + 12345 + index) & 0xFFFFFFFFFFFFFFFF
        values.append((seed % 10000) / 10000.0 - 0.5)
    return _normalize_vector(values)


class FastEmbedProvider(EmbeddingProvider):
    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._dimension: int | None = None

    @property
    def provider_name(self) -> str:
        return "fastembed"

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=self._model_name)
        self._dimension = TextEmbedding.get_embedding_size(self._model_name)

    def embed_text(self, text: str) -> list[float]:
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        assert self._model is not None
        return [vector.tolist() for vector in self._model.embed(texts)]

    def get_dimension(self) -> int:
        self._ensure_model()
        assert self._dimension is not None
        return self._dimension


class OpenAICompatibleProvider(EmbeddingProvider):
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        dimension: int,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._dimension = dimension

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    def embed_text(self, text: str) -> list[float]:
        vectors = self.embed_batch([text])
        return vectors[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise EmbeddingServiceError("EMBEDDING_API_KEY 未配置")
        if not self._base_url:
            raise EmbeddingServiceError("EMBEDDING_BASE_URL 未配置")

        import httpx

        response = httpx.post(
            f"{self._base_url}/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "input": texts},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload["data"], key=lambda item: item["index"])
        return [item["embedding"] for item in data]

    def get_dimension(self) -> int:
        return self._dimension


class MockEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    @property
    def provider_name(self) -> str:
        return "mock"

    def embed_text(self, text: str) -> list[float]:
        return _stable_mock_vector(text, self._dimension)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [_stable_mock_vector(text, self._dimension) for text in texts]

    def get_dimension(self) -> int:
        return self._dimension


class EmbeddingService:
    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or _create_provider()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    def embed_text(self, text: str) -> list[float]:
        return self._provider.embed_text(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_batch(texts)

    def get_dimension(self) -> int:
        actual = self._provider.get_dimension()
        configured = settings.embedding_dimension
        if actual != configured:
            print(
                f"[WARN] Embedding dimension mismatch: provider={actual}, "
                f"settings.embedding_dimension={configured}. "
                "Please align EMBEDDING_DIMENSION in .env or run rebuild_qdrant.py --recreate."
            )
        return actual


def _create_provider() -> EmbeddingProvider:
    provider = settings.embedding_provider.lower()
    if provider == "fastembed":
        return FastEmbedProvider(settings.embedding_model)
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            dimension=settings.embedding_dimension,
        )
    if provider == "mock":
        return MockEmbeddingProvider(settings.embedding_dimension)
    raise EmbeddingServiceError(f"不支持的 EMBEDDING_PROVIDER: {settings.embedding_provider}")


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
