"""知识卡片重复检测服务：embedding + Qdrant 相似检索与预警日志。"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.rag.qdrant_vector_store import QdrantVectorStore, QdrantVectorStoreError, get_qdrant_vector_store
from app.rag.vector_payload_builder import build_vector_text
from app.repositories.knowledge_duplicate_check_repository import KnowledgeDuplicateCheckRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.duplicate_check_schema import DuplicateCheckItem, DuplicateCheckResult

logger = logging.getLogger(__name__)

# 重复检测相似度阈值（集中定义，避免散落硬编码）
_HIGH_DUPLICATE_THRESHOLD = 0.92
_SUSPECTED_DUPLICATE_THRESHOLD = 0.85
_RELATED_THRESHOLD = 0.78

_LEVEL_NAMES = {
    "high_duplicate": "高度重复",
    "suspected_duplicate": "疑似重复",
    "related": "相关知识",
    "none": "未发现明显重复",
}

_SUGGESTIONS = {
    "high_duplicate": "建议优先查看已有卡片，考虑合并或更新已有卡片",
    "suspected_duplicate": "建议人工确认是否重复",
    "related": "可作为参考知识",
    "none": "可正常提交审核",
}


class DuplicateCheckError(Exception):
    """重复检测执行失败（Qdrant / embedding 不可用等）。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DuplicateCheckService:
    """知识卡片重复检测服务。

    用于在知识卡片提交审核前，通过 embedding + Qdrant 检索发现已有相似知识。
    本服务只做预警和日志记录，不负责阻断提交、不负责合并卡片。
    """

    DEFAULT_TOP_K = 5

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.knowledge_repo = KnowledgeRepository(session)
        self.duplicate_repo = KnowledgeDuplicateCheckRepository(session)
        self.embedding = embedding_client or EmbeddingClient(self.settings)
        self.vector_store = vector_store or get_qdrant_vector_store()

    def check_card_by_id(
        self,
        card_id: int,
        *,
        operator_user: str | None = None,
        source_type: str = "card_submit",
    ) -> DuplicateCheckResult:
        """按知识卡片 ID 执行重复检测。"""
        card = self.knowledge_repo.get_active_by_id(card_id)
        if card is None:
            raise DuplicateCheckError(f"知识卡片不存在：{card_id}")
        return self.check_card_object(card, operator_user=operator_user, source_type=source_type)

    def check_card_object(
        self,
        card: KnowledgeCard,
        *,
        operator_user: str | None = None,
        source_type: str = "card_submit",
        save_logs: bool = True,
    ) -> DuplicateCheckResult:
        """对传入的知识卡片对象执行重复检测（同步入口，供 Router / Service 调用）。"""
        try:
            result = asyncio.run(
                self._check_card_async(
                    card,
                    operator_user=operator_user,
                    source_type=source_type,
                    save_logs=save_logs,
                )
            )
            return result
        except DuplicateCheckError:
            raise
        except (EmbeddingClientError, QdrantVectorStoreError) as exc:
            raise DuplicateCheckError(f"重复检测失败：{exc}") from exc
        except RuntimeError as exc:
            if "asyncio.run()" in str(exc):
                raise DuplicateCheckError(
                    "重复检测失败：当前已在异步上下文中，请改用 check_card_object_async"
                ) from exc
            logger.exception("重复检测异常 card_id=%s", card.id)
            raise DuplicateCheckError(f"重复检测失败：{exc}") from exc
        except Exception as exc:
            logger.exception("重复检测异常 card_id=%s", card.id)
            raise DuplicateCheckError(f"重复检测失败：{exc}") from exc

    async def check_card_object_async(
        self,
        card: KnowledgeCard,
        *,
        operator_user: str | None = None,
        source_type: str = "card_submit",
        save_logs: bool = True,
    ) -> DuplicateCheckResult:
        """对传入的知识卡片对象执行重复检测（异步入口，供 LangGraph 等 async 节点调用）。"""
        try:
            return await self._check_card_async(
                card,
                operator_user=operator_user,
                source_type=source_type,
                save_logs=save_logs,
            )
        except DuplicateCheckError:
            raise
        except (EmbeddingClientError, QdrantVectorStoreError) as exc:
            raise DuplicateCheckError(f"重复检测失败：{exc}") from exc
        except Exception as exc:
            logger.exception("重复检测异常 card_id=%s", card.id)
            raise DuplicateCheckError(f"重复检测失败：{exc}") from exc

    async def _check_card_async(
        self,
        card: KnowledgeCard,
        *,
        operator_user: str | None,
        source_type: str,
        save_logs: bool,
    ) -> DuplicateCheckResult:
        check_text = self.build_check_text(card)
        vector = await self._embed_text(check_text)
        raw_hits = self.search_similar_cards(
            vector,
            exclude_card_id=card.id,
            top_k=self.DEFAULT_TOP_K,
        )

        items: list[DuplicateCheckItem] = []
        for hit in raw_hits:
            kid = int(hit["knowledge_id"])
            # 排除当前卡片自身，避免编辑后提交时把自己识别为高度重复
            if kid == card.id:
                continue
            candidate = self.knowledge_repo.get_duplicate_candidate_by_id(kid)
            if candidate is None:
                continue
            score = float(hit["score"])
            level, level_name, suggestion = self.classify_score(score)
            if level == "none":
                continue
            items.append(
                DuplicateCheckItem(
                    candidate_card_id=candidate.id,
                    candidate_title=candidate.title,
                    system_name=candidate.system_name,
                    module_name=candidate.module_name,
                    audit_status=candidate.audit_status,
                    similarity_score=score,
                    check_level=level,
                    check_level_name=level_name,
                    suggestion=suggestion,
                )
            )

        highest_score = max((item.similarity_score or 0.0 for item in items), default=None)
        if items:
            top_item = max(items, key=lambda x: x.similarity_score or 0.0)
            highest_level = top_item.check_level
            highest_level_name = top_item.check_level_name
        else:
            highest_level = "none"
            highest_level_name = _LEVEL_NAMES["none"]

        has_high_risk = any(item.check_level == "high_duplicate" for item in items)
        message = self._build_message(highest_level, has_high_risk)

        result = DuplicateCheckResult(
            source_card_id=card.id,
            source_title=card.title,
            highest_score=highest_score,
            highest_level=highest_level,
            highest_level_name=highest_level_name,
            has_high_risk_duplicate=has_high_risk,
            items=items,
            message=message,
        )

        if save_logs:
            self.save_check_logs(result, operator_user=operator_user, source_type=source_type)

        return result

    def build_check_text(self, card: KnowledgeCard) -> str:
        """拼接用于重复检测的文本（复用向量同步全文拼接逻辑）。"""
        return build_vector_text(card)

    async def _embed_text(self, text: str) -> list[float]:
        """生成检测文本 embedding；本地模式走同步 fastembed，远程走异步客户端。"""
        if self.settings.qdrant_mode.lower() == "local":
            from app.rag.embedding_service import get_embedding_service

            return get_embedding_service().embed_text(text)
        return await self.embedding.embed_text(text)

    def search_similar_cards(
        self,
        vector: list[float],
        *,
        exclude_card_id: int | None,
        top_k: int = 5,
    ) -> list[dict]:
        """调用 Qdrant 查询相似知识，返回 knowledge_id 与 score。"""
        if self.settings.qdrant_mode.lower() == "local":
            from app.rag.qdrant_store import get_qdrant_store

            hits = get_qdrant_store().search_by_vector(vector, top_k=top_k + 1)
            raw = [
                {"knowledge_id": hit.card_id, "score": hit.score, "payload": hit.payload}
                for hit in hits
            ]
        else:
            raw = self.vector_store.search(vector, top_k=top_k + 1, score_threshold=None)

        if exclude_card_id is None:
            return raw[:top_k]
        filtered = [h for h in raw if int(h["knowledge_id"]) != exclude_card_id]
        return filtered[:top_k]

    def classify_score(self, score: float | None) -> tuple[str, str, str]:
        """根据相似度分数返回重复等级、中文名称和处理建议。"""
        if score is None:
            return "none", _LEVEL_NAMES["none"], _SUGGESTIONS["none"]
        if score >= _HIGH_DUPLICATE_THRESHOLD:
            level = "high_duplicate"
        elif score >= _SUSPECTED_DUPLICATE_THRESHOLD:
            level = "suspected_duplicate"
        elif score >= _RELATED_THRESHOLD:
            level = "related"
        else:
            level = "none"
        return level, _LEVEL_NAMES[level], _SUGGESTIONS[level]

    def save_check_logs(
        self,
        result: DuplicateCheckResult,
        *,
        operator_user: str | None,
        source_type: str,
    ) -> None:
        """将检测结果写入 knowledge_duplicate_check_log。"""
        logs: list[KnowledgeDuplicateCheckLog] = []

        if not result.items:
            logs.append(
                KnowledgeDuplicateCheckLog(
                    source_card_id=result.source_card_id,
                    source_type=source_type,
                    candidate_card_id=None,
                    similarity_score=None,
                    check_level="none",
                    check_result="no_duplicate",
                    operator_user=operator_user,
                )
            )
        else:
            for item in result.items:
                logs.append(
                    KnowledgeDuplicateCheckLog(
                        source_card_id=result.source_card_id,
                        source_type=source_type,
                        candidate_card_id=item.candidate_card_id,
                        similarity_score=Decimal(str(item.similarity_score)) if item.similarity_score is not None else None,
                        check_level=item.check_level,
                        check_result="duplicate_warning",
                        operator_user=operator_user,
                    )
                )

        self.duplicate_repo.create_many(logs)
        self.session.flush()

    @staticmethod
    def _build_message(highest_level: str, has_high_risk: bool) -> str:
        if has_high_risk:
            return "发现高度相似知识，请管理员审核时重点确认。"
        if highest_level == "suspected_duplicate":
            return "发现疑似重复知识，请人工确认。"
        if highest_level == "related":
            return "发现相关知识，可作为参考。"
        return "未发现明显重复，可正常提交审核。"
