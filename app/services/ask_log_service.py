"""Question log and unanswered question persistence for /api/ask."""

from __future__ import annotations

import time
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.models.question_log import QuestionLog
from app.models.unanswered_question import UnansweredQuestion
from app.repositories.question_repository import QuestionRepository
from app.repositories.unanswered_repository import UnansweredRepository


class AskLogService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.question_repo = QuestionRepository(session)
        self.unanswered_repo = UnansweredRepository(session)

    def write_log(self, state: AskState) -> int | None:
        if not state.get("should_write_log", False):
            return None

        started_at = state.get("started_at") or time.perf_counter()
        latency_ms = int((time.perf_counter() - started_at) * 1000)

        question_log = self.create_question_log(state, latency_ms=latency_ms)
        question_log_id = question_log.id

        matched = state.get("matched", False)
        retrieval_error = state.get("retrieval_error", False)
        if not matched and not retrieval_error:
            self.upsert_unanswered_question(state, question_log_id=question_log_id)

        self.question_repo.save()
        return question_log_id

    def create_question_log(self, state: AskState, *, latency_ms: int) -> QuestionLog:
        matched = state.get("matched", False)
        log = QuestionLog(
            request_id=uuid.uuid4().hex,
            question_raw=state.get("question_raw") or "",
            question_masked=state.get("question_masked") or "",
            rewritten_question=state.get("rewritten_question") or state.get("question_masked") or "",
            user_id=state.get("user_id") or "anonymous",
            group_id=state.get("group_id") or "demo_group",
            source_type=state.get("source_type") or "web",
            intent=state.get("intent") or "question",
            matched=1 if matched else 0,
            matched_card_ids=state.get("matched_card_ids") or None,
            similarity_score=Decimal(str(state.get("similarity_score") or 0.0)),
            answer=state.get("answer") or "",
            fallback_reason=state.get("fallback_reason"),
            need_human=1 if state.get("need_human", False) else 0,
            risk_level=state.get("risk_level") or "low",
            latency_ms=latency_ms,
            retrieval_time_ms=state.get("retrieval_time_ms") or 0,
            answer_time_ms=state.get("answer_time_ms") or 0,
            llm_tokens=state.get("llm_tokens"),
            error_stage=state.get("error_stage"),
            error_message=state.get("error_message"),
            langsmith_trace_id=None,
        )
        return self.question_repo.create_log(log)

    def upsert_unanswered_question(self, state: AskState, *, question_log_id: int) -> None:
        question_masked = state.get("question_masked") or ""
        normalized_question = question_masked.strip()[:500]
        summary = question_masked[:100]
        existing = self.unanswered_repo.get_pending_by_normalized(normalized_question)
        if existing is not None:
            self.unanswered_repo.increment_frequency(existing, question_log_id=question_log_id)
        else:
            record = UnansweredQuestion(
                question_log_id=question_log_id,
                question=question_masked,
                normalized_question=normalized_question,
                summary=summary,
                system_name="",
                module_name="",
                tags="",
                frequency=1,
                status="pending",
            )
            self.unanswered_repo.create(record)
