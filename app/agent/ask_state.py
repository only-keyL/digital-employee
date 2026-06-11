"""AskState definition for LangGraph workflow (Phase 7)."""

from __future__ import annotations

from typing import Any, TypedDict


class AskState(TypedDict, total=False):
    # --- input ---
    question_raw: str
    question_masked: str
    rewritten_question: str
    user_id: str
    group_id: str
    source_type: str

    # --- flow control ---
    is_valid: bool
    should_write_log: bool
    route: str
    retrieval_error: bool

    # --- retrieval (internal + response) ---
    matched: bool
    similarity_score: float
    sources: list[dict[str, Any]]
    matched_card_ids: str
    retrieval_hits: list[dict[str, Any]]
    fallback_reason: str | None

    # --- raw retrieval fields (node-internal) ---
    _raw_matched: bool
    _raw_fallback_reason: str | None
    _raw_similarity_score: float

    # --- generation ---
    answer: str
    need_human: bool
    risk_level: str
    llm_tokens: int | None
    error_stage: str | None
    error_message: str | None

    # --- timing ---
    started_at: float
    retrieval_time_ms: int
    answer_time_ms: int
    latency_ms: int

    # --- output ---
    question_log_id: int | None
    intent: str
