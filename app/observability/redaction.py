"""Safe metadata construction for LangSmith tracing (no PII / secrets)."""

from __future__ import annotations

from typing import Any

from app.agent.ask_state import AskState
from app.config.settings import get_settings

_FALLBACK_REASON_MAX_LEN = 120


def build_safe_metadata(state: AskState) -> dict[str, Any]:
    """构建可安全上报 LangSmith 的元数据（不含原文、密钥等敏感信息）。"""
    settings = get_settings()

    question_raw = state.get("question_raw") or ""
    question_masked = state.get("question_masked") or ""
    question_length = len(question_raw) or len(question_masked)

    fallback_reason = state.get("fallback_reason")
    if isinstance(fallback_reason, str) and len(fallback_reason) > _FALLBACK_REASON_MAX_LEN:
        fallback_reason = fallback_reason[:_FALLBACK_REASON_MAX_LEN]

    metadata: dict[str, Any] = {
        "question_length": question_length,
        "matched": bool(state.get("matched", False)),
        "similarity_score": float(state.get("similarity_score") or 0.0),
        "retrieval_time_ms": int(state.get("retrieval_time_ms") or 0),
        "answer_time_ms": int(state.get("answer_time_ms") or 0),
        "latency_ms": int(state.get("latency_ms") or 0),
        "risk_level": state.get("risk_level") or "low",
        "need_human": bool(state.get("need_human", False)),
        "fallback_reason": fallback_reason,
        "source_type": state.get("source_type") or "web",
        "provider": settings.llm_provider,
        "status": "ok" if not state.get("error_stage") else "error",
    }

    llm_tokens = state.get("llm_tokens")
    if llm_tokens is not None:
        metadata["llm_tokens"] = llm_tokens

    node_name = state.get("node_name")
    if node_name:
        metadata["node_name"] = node_name

    return metadata
