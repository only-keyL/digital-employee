"""Ask service: LangGraph orchestration entry for /api/ask."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.agent.graph_runner import AskGraphRunner
from app.schemas.ask_schema import AskRequest, AskResponse, AskSourceItem


class AskService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ask(self, payload: AskRequest) -> AskResponse:
        initial_state = self._build_initial_state(payload)
        final_state = AskGraphRunner(self.session).run(initial_state)
        return self._map_state_to_response(final_state)

    def _build_initial_state(self, payload: AskRequest) -> AskState:
        return {
            "question_raw": payload.question or "",
            "user_id": payload.user_id or "anonymous",
            "group_id": payload.group_id or "demo_group",
            "source_type": payload.source_type or "web",
            "started_at": time.perf_counter(),
            "is_valid": False,
            "should_write_log": False,
            "retrieval_error": False,
            "matched": False,
            "similarity_score": 0.0,
            "sources": [],
            "retrieval_hits": [],
            "matched_card_ids": "",
            "answer": "",
            "need_human": False,
            "risk_level": "low",
            "question_log_id": None,
            "fallback_reason": None,
            "intent": "question",
            "retrieval_time_ms": 0,
            "answer_time_ms": 0,
            "llm_tokens": None,
            "error_stage": None,
            "error_message": None,
        }

    def _map_state_to_response(self, state: AskState) -> AskResponse:
        sources = [
            AskSourceItem(
                card_id=int(item.get("card_id") or 0),
                title=item.get("title") or "",
                score=float(item.get("score") or 0.0),
            )
            for item in (state.get("sources") or [])
        ]
        return AskResponse(
            matched=bool(state.get("matched", False)),
            answer=state.get("answer") or "",
            sources=sources,
            similarity_score=float(state.get("similarity_score") or 0.0),
            question_log_id=state.get("question_log_id"),
            fallback_reason=state.get("fallback_reason"),
            need_human=bool(state.get("need_human", False)),
            risk_level=state.get("risk_level") or "low",
        )
