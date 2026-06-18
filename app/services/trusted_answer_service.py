"""可信回答包装服务：统一来源展示、置信度提示与 question_log 字段归一化。"""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.confidence import classify_confidence
from app.services.retrieval_service import RetrievalHit

# 低置信度 / 未命中时返回给用户的固定话术
_LOW_CONFIDENCE_ANSWER = "当前知识库没有足够依据，已记录为未命中问题。"

# 置信度等级中文映射
_CONFIDENCE_CN = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "none": "无",
}


@dataclass
class PrimarySource:
    """top1 知识来源摘要，用于可信回答展示与日志回填。"""

    card_id: int | None
    title: str | None
    score: float
    system_name: str | None
    module_name: str | None
    confidence_level: str


@dataclass
class TrustedLogPatch:
    """question_log 可信回答相关字段补丁。"""

    primary_matched_card_id: int | None
    primary_matched_card_title: str | None
    confidence_level: str
    answer_status: str
    answer_source: str | None
    system_name: str | None
    module_name: str | None


class TrustedAnswerService:
    """可信回答包装服务。

    负责把 RAG 原始答案包装成带来源、相似度、置信度和反馈提示的用户可读答案。
    本类不调用大模型，不访问 Qdrant，只做结果归一化和展示包装。
    """

    def get_primary_source(
        self,
        *,
        hits: list[RetrievalHit] | None = None,
        hit_dicts: list[dict] | None = None,
        score: float = 0.0,
        confidence_level: str | None = None,
    ) -> PrimarySource | None:
        """从检索 hits 或轻量 dict 列表中提取 top1 知识来源。"""
        if hits:
            top = hits[0]
            level = confidence_level or classify_confidence(top.score)
            return PrimarySource(
                card_id=int(top.card.id),
                title=top.title or top.card.title,
                score=float(top.score),
                system_name=top.card.system_name,
                module_name=top.card.module_name,
                confidence_level=level,
            )

        if hit_dicts:
            top = hit_dicts[0]
            card_id = top.get("card_id")
            level = confidence_level or classify_confidence(float(top.get("score") or score))
            return PrimarySource(
                card_id=int(card_id) if card_id is not None else None,
                title=top.get("title"),
                score=float(top.get("score") or score),
                system_name=top.get("system_name"),
                module_name=top.get("module_name"),
                confidence_level=level,
            )
        return None

    def get_primary_source_from_context(
        self,
        context: object | None,
        *,
        score: float = 0.0,
        confidence_level: str | None = None,
    ) -> PrimarySource | None:
        """从 RagContextItem 提取 top1 来源（AskGraphV2 路径使用）。"""
        if context is None:
            return None
        level = confidence_level or getattr(context, "confidence_level", None) or classify_confidence(score)
        card = getattr(context, "card", None)
        return PrimarySource(
            card_id=int(getattr(context, "knowledge_id", 0) or 0) or None,
            title=getattr(context, "title", None),
            score=float(getattr(context, "score", score) or score),
            system_name=getattr(card, "system_name", None) if card else None,
            module_name=getattr(card, "module_name", None) if card else None,
            confidence_level=level,
        )

    def build_trusted_answer(
        self,
        *,
        raw_answer: str,
        confidence_level: str,
        primary_source: PrimarySource | None,
        matched: bool,
        llm_failed: bool = False,
    ) -> str:
        """根据回答、检索上下文和置信度构造最终返回给用户的可信回答文本。"""
        if llm_failed:
            # LLM 失败时不拼接虚假来源，保留降级话术
            return (raw_answer or "").strip() or _LOW_CONFIDENCE_ANSWER

        # 低置信度或未命中：不强答，不展示虚假来源
        if not matched or confidence_level == "low":
            return _LOW_CONFIDENCE_ANSWER

        if confidence_level not in {"high", "medium"} or primary_source is None:
            return _LOW_CONFIDENCE_ANSWER

        body = (raw_answer or "").strip()
        parts = [
            "【数字员工回答】",
            body,
            "",
            "【参考知识】",
            f"知识卡片：{primary_source.title or '未知'}",
            f"所属系统：{primary_source.system_name or '未知'}",
            f"所属模块：{primary_source.module_name or '未知'}",
            f"命中相似度：{primary_source.score:.4f}",
            f"可信度：{_CONFIDENCE_CN.get(confidence_level, confidence_level)}",
            "审核状态：已审核",
            "",
            "【反馈】",
            "回复「有用」表示已解决；",
            "回复「无用：原因」表示未解决；",
            "回复「补充：你的正确答案」可以提交修订建议。",
        ]

        # 中置信度答案可以返回，但必须提醒用户结合实际场景人工确认
        if confidence_level == "medium":
            parts.extend(
                [
                    "",
                    "【提示】",
                    "当前答案为中置信度匹配，建议结合实际业务场景人工确认。",
                ]
            )

        return "\n".join(parts)

    def build_log_patch(
        self,
        *,
        confidence_level: str,
        matched: bool,
        primary_source: PrimarySource | None,
        retrieval_error: bool = False,
        llm_failed: bool = False,
    ) -> TrustedLogPatch:
        """根据检索结果构造 question_log 需要回填的增强字段。"""
        if retrieval_error:
            return TrustedLogPatch(
                primary_matched_card_id=None,
                primary_matched_card_title=None,
                confidence_level=confidence_level or "none",
                answer_status="error",
                answer_source="system_fallback",
                system_name=None,
                module_name=None,
            )

        if llm_failed:
            return TrustedLogPatch(
                primary_matched_card_id=primary_source.card_id if primary_source else None,
                primary_matched_card_title=primary_source.title if primary_source else None,
                confidence_level=confidence_level or "none",
                answer_status="llm_failed",
                answer_source="llm_fallback",
                system_name=primary_source.system_name if primary_source else None,
                module_name=primary_source.module_name if primary_source else None,
            )

        if matched and confidence_level == "high":
            answer_status = "hit"
            answer_source = "qdrant_rag"
        elif matched and confidence_level == "medium":
            answer_status = "medium_confidence"
            answer_source = "qdrant_rag"
        elif confidence_level == "low":
            answer_status = "low_confidence"
            answer_source = "unanswered"
        else:
            answer_status = "miss"
            answer_source = "unanswered"

        return TrustedLogPatch(
            primary_matched_card_id=primary_source.card_id if primary_source else None,
            primary_matched_card_title=primary_source.title if primary_source else None,
            confidence_level=confidence_level or "none",
            answer_status=answer_status,
            answer_source=answer_source,
            system_name=primary_source.system_name if primary_source else None,
            module_name=primary_source.module_name if primary_source else None,
        )

    @staticmethod
    def low_confidence_answer() -> str:
        """返回低置信度拒答固定话术。"""
        return _LOW_CONFIDENCE_ANSWER
