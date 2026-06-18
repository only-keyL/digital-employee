"""RAG 向量存储抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VectorStore(ABC):
    """Qdrant 向量存储抽象，供 Stage3 RAG 使用。"""

    @abstractmethod
    def ensure_collection(self, vector_size: int) -> None:
        pass

    @abstractmethod
    def upsert_knowledge(self, knowledge_id: int, vector: list[float], payload: dict[str, Any]) -> None:
        pass

    @abstractmethod
    def delete_knowledge(self, knowledge_id: int) -> None:
        pass

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        top_k: int,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        pass
