"""LangGraph 问答工作流节点（阶段七）。"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.agent.constants import (
    EMPTY_QUESTION_REASON,
    FALLBACK_ANSWER,
    RETRIEVAL_ERROR_ANSWER,
    RETRIEVAL_ERROR_REASON,
)
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.answer_generation_service import AnswerGenerationService
from app.services.ask_log_service import AskLogService
from app.services.retrieval_service import RetrievalHit, RetrievalService


def _get_db_session(config: RunnableConfig) -> Session:
    """从 LangGraph RunnableConfig 取出当前请求的 SQLAlchemy Session。"""
    configurable = config.get("configurable") or {}
    session = configurable.get("db")
    if session is None:
        raise ValueError("Graph 节点需要 configurable['db'] 注入当前请求 Session")
    return session


def _hits_from_state(state: AskState, session: Session) -> list[RetrievalHit]:
    """将 state 中的 retrieval_hits 还原为带 ORM 对象的 RetrievalHit 列表。"""
    repo = KnowledgeRepository(session)
    hits: list[RetrievalHit] = []
    for item in state.get("retrieval_hits") or []:
        card_id = item.get("card_id")
        if card_id is None:
            continue
        card = repo.get_searchable_by_id(int(card_id))
        if card is None:
            continue
        hits.append(
            RetrievalHit(
                card=card,
                title=item.get("title") or card.title,
                score=float(item.get("score") or 0.0),
            )
        )
    return hits


def validate_input_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：校验问题非空；空问题不写日志并直接结束。"""
    question = (state.get("question_raw") or "").strip()
    if not question:
        return {
            "is_valid": False,
            "should_write_log": False,
            "matched": False,
            "answer": "",
            "sources": [],
            "similarity_score": 0.0,
            "question_log_id": None,
            "fallback_reason": EMPTY_QUESTION_REASON,
            "need_human": False,
            "risk_level": "low",
            "intent": "question",
            "route": "end",
        }
    return {
        "is_valid": True,
        "should_write_log": True,
        "question_raw": question,
        "route": "continue",
    }


def preprocess_question_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：填充 question_masked / rewritten_question 等字段（当前为占位实现）。"""
    question = state.get("question_raw") or ""
    return {
        "question_masked": question,
        "rewritten_question": question,
        "intent": "question",
        "user_id": state.get("user_id") or "anonymous",
        "group_id": state.get("group_id") or "demo_group",
        "source_type": state.get("source_type") or "web",
    }


def retrieve_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：调用 RetrievalService 做 Qdrant 向量检索。"""
    session = _get_db_session(config)
    question_masked = state.get("question_masked") or ""
    retrieval_started = time.perf_counter()
    retrieval = RetrievalService(session).retrieve(question_masked)
    retrieval_time_ms = int((time.perf_counter() - retrieval_started) * 1000)

    if retrieval.error is not None:
        return {
            "retrieval_error": True,
            "retrieval_time_ms": retrieval_time_ms,
            "matched": False,
            "similarity_score": 0.0,
            "sources": [],
            "retrieval_hits": [],
            "matched_card_ids": "",
            "fallback_reason": RETRIEVAL_ERROR_REASON,
            "error_message": retrieval.error,
            "route": "error",
        }

    hits_dicts = [
        {"card_id": hit.card.id, "title": hit.title, "score": hit.score}
        for hit in retrieval.hits
    ]
    return {
        "retrieval_error": False,
        "retrieval_time_ms": retrieval_time_ms,
        "_raw_matched": retrieval.matched,
        "_raw_fallback_reason": retrieval.fallback_reason,
        "_raw_similarity_score": retrieval.similarity_score,
        "retrieval_hits": hits_dicts,
        "route": "ok",
    }


def match_judge_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：根据检索原始结果写入 matched、sources、similarity_score。"""
    matched = bool(state.get("_raw_matched", False))
    similarity_score = float(state.get("_raw_similarity_score") or 0.0)
    fallback_reason = state.get("_raw_fallback_reason")
    hits = state.get("retrieval_hits") or []

    if matched:
        sources = [
            {"card_id": int(h["card_id"]), "title": h.get("title") or "", "score": float(h.get("score") or 0.0)}
            for h in hits
        ]
        matched_card_ids = ",".join(str(h["card_id"]) for h in hits)
        return {
            "matched": True,
            "sources": sources,
            "matched_card_ids": matched_card_ids,
            "similarity_score": similarity_score,
            "fallback_reason": None,
            "route": "matched",
        }

    return {
        "matched": False,
        "sources": [],
        "matched_card_ids": "",
        "similarity_score": similarity_score,
        "fallback_reason": fallback_reason or "向量检索未命中",
        "route": "miss",
    }


def generate_answer_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：命中后调用 AnswerGenerationService 生成 LLM 答案。"""
    session = _get_db_session(config)
    question_masked = state.get("question_masked") or ""
    hits = _hits_from_state(state, session)
    generated = AnswerGenerationService().generate(question=question_masked, hits=hits)
    return {
        "answer": generated.answer,
        "llm_tokens": generated.llm_tokens,
        "answer_time_ms": generated.answer_time_ms,
        "fallback_reason": generated.fallback_reason,
        "need_human": generated.need_human,
        "risk_level": generated.risk_level,
        "error_stage": generated.error_stage,
        "error_message": generated.error_message,
    }


def handle_miss_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：未命中时返回固定 FALLBACK_ANSWER，不调用 LLM。"""
    return {
        "answer": FALLBACK_ANSWER,
        "need_human": False,
        "risk_level": "low",
        "llm_tokens": None,
        "answer_time_ms": 0,
        "error_stage": None,
        "error_message": None,
    }


def error_fallback_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：检索异常时的固定兜底回答。"""
    return {
        "answer": RETRIEVAL_ERROR_ANSWER,
        "matched": False,
        "sources": [],
        "matched_card_ids": "",
        "similarity_score": 0.0,
        "fallback_reason": RETRIEVAL_ERROR_REASON,
        "need_human": True,
        "risk_level": "medium",
        "llm_tokens": None,
        "answer_time_ms": 0,
        "error_stage": None,
    }


def write_log_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：写入 question_log 与 unanswered_question，返回 question_log_id。"""
    session = _get_db_session(config)
    started_at = state.get("started_at") or time.perf_counter()
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    question_log_id = AskLogService(session).write_log(state)
    return {
        "question_log_id": question_log_id,
        "latency_ms": latency_ms,
    }
