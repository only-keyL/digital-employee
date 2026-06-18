"""Stage3 RAG 置信度分级工具。"""

from __future__ import annotations

from app.config.settings import Settings, get_settings


def classify_confidence(score: float, settings: Settings | None = None) -> str:
    """根据 top_score 计算 high / medium / low。"""
    cfg = settings or get_settings()
    if score >= cfg.rag_high_confidence_threshold:
        return "high"
    if score >= cfg.similarity_threshold:
        return "medium"
    return "low"
