"""Stage3 问答日志落库：ask_run / retrieval_log / llm_call_log / question_log。"""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.desensitize import sanitize_text
from app.models.ask_run import AskRun
from app.models.llm_call_log import LlmCallLog
from app.models.question_log import QuestionLog
from app.models.retrieval_log import RetrievalLog
from app.rag.confidence import classify_confidence
from app.rag.rag_retrieval_service import RagRetrievalResult, RagRetrievalService
from app.repositories.question_repository import QuestionRepository
from app.repositories.stage3_repository import AskRunRepository, LlmCallLogRepository, RetrievalLogRepository
from app.repositories.unanswered_repository import UnansweredRepository
from app.services.trusted_answer_service import TrustedAnswerService


class AskRunLogService:
    """AskGraphV2 运行过程的结构化日志写入，并同步 question_log。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.ask_run_repo = AskRunRepository(session)
        self.retrieval_repo = RetrievalLogRepository(session)
        self.llm_repo = LlmCallLogRepository(session)
        self.unanswered_repo = UnansweredRepository(session)
        self.question_repo = QuestionRepository(session)
        self.trusted_service = TrustedAnswerService()

    def create_run(
        self,
        *,
        run_id: str,
        question: str,
        normalized_question: str,
        source: str,
        user_id: str | None,
    ) -> AskRun:
        record = AskRun(
            run_id=run_id,
            question=question,
            normalized_question=normalized_question,
            source=source,
            user_id=user_id,
            status="running",
            confidence_level="none",
        )
        return self.ask_run_repo.create(record)

    def save_retrieval_logs(self, run_id: str, retrieval: RagRetrievalResult) -> None:
        records: list[RetrievalLog] = []
        for hit in retrieval.raw_hits:
            kid = int(hit.get("knowledge_id", 0))
            score = float(hit.get("score", 0.0))
            records.append(
                RetrievalLog(
                    run_id=run_id,
                    knowledge_id=kid,
                    rank=int(hit.get("rank", 0)),
                    score=score,
                    confidence_level=classify_confidence(score),
                    collection_name=str(hit.get("collection_name") or ""),
                    payload_snapshot=RagRetrievalService.payload_snapshot(hit),
                )
            )
        if records:
            self.retrieval_repo.bulk_create(records)

    def save_llm_log(
        self,
        *,
        run_id: str,
        provider: str,
        model: str,
        status: str,
        prompt: str = "",
        response: str = "",
        error_code: str | None = None,
        error_message: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest() if prompt else None
        self.llm_repo.create(
            LlmCallLog(
                run_id=run_id,
                provider=provider,
                model=model,
                status=status,
                prompt_hash=prompt_hash,
                prompt_preview=sanitize_text(prompt, max_length=200) if prompt else None,
                response_preview=sanitize_text(response, max_length=200) if response else None,
                error_code=error_code,
                error_message=error_message,
                latency_ms=latency_ms,
            )
        )

    def finalize_run(
        self,
        run: AskRun,
        *,
        answer: str | None,
        status: str,
        confidence_level: str,
        top_score: float | None,
        fallback_reason: str | None,
        latency_ms: int,
        write_unanswered: bool = False,
    ) -> None:
        run.answer = answer
        run.status = status
        run.confidence_level = confidence_level
        run.top_score = top_score
        run.fallback_reason = fallback_reason
        run.latency_ms = latency_ms
        self.ask_run_repo.save()

        if write_unanswered:
            normalized = (run.normalized_question or "").strip()[:500]
            existing = self.unanswered_repo.get_pending_by_normalized(normalized)
            if existing is None:
                from app.models.unanswered_question import UnansweredQuestion
                from datetime import datetime

                self.unanswered_repo.create(
                    UnansweredQuestion(
                        question=sanitize_text(run.question, max_length=500),
                        summary=sanitize_text(run.question, max_length=100),
                        normalized_question=normalized,
                        status="pending",
                        frequency=1,
                        last_seen_time=datetime.now(),
                    )
                )
            else:
                existing.frequency += 1
                from datetime import datetime
                existing.last_seen_time = datetime.now()
                self.session.flush()

        self.session.flush()

    def create_question_log_from_v2_state(
        self,
        state: dict,
        *,
        latency_ms: int,
        write_unanswered: bool = False,
    ) -> int | None:
        """根据 AskGraphV2 最终状态写入 question_log，支撑可信回答和后续反馈闭环。"""
        question = (state.get("normalized_question") or state.get("question") or "").strip()
        if not question:
            return None

        confidence_level = state.get("confidence_level") or "none"
        status = state.get("status") or "failed"
        matched = status == "success" and confidence_level in {"high", "medium"}
        contexts = state.get("contexts") or []
        primary = self.trusted_service.get_primary_source_from_context(
            contexts[0] if contexts else None,
            score=float(state.get("top_score") or 0.0),
            confidence_level=confidence_level,
        )
        log_patch = self.trusted_service.build_log_patch(
            confidence_level=confidence_level,
            matched=matched,
            primary_source=primary,
            llm_failed=status == "llm_failed",
        )

        matched_card_ids = None
        if contexts:
            matched_card_ids = ",".join(str(ctx.knowledge_id) for ctx in contexts[:3])

        log = QuestionLog(
            request_id=state.get("run_id") or uuid.uuid4().hex,
            question_raw=state.get("question") or question,
            question_masked=question,
            rewritten_question=question,
            user_id=state.get("user_id") or "anonymous",
            group_id=None,
            source_type=state.get("source") or "api_ask_v2",
            intent="question",
            matched=1 if matched else 0,
            matched_card_ids=matched_card_ids,
            primary_matched_card_id=state.get("primary_matched_card_id") or log_patch.primary_matched_card_id,
            primary_matched_card_title=state.get("primary_matched_card_title") or log_patch.primary_matched_card_title,
            similarity_score=Decimal(str(state.get("top_score") or 0.0)),
            confidence_level=log_patch.confidence_level,
            answer_status=state.get("answer_status") or log_patch.answer_status,
            answer_source=state.get("answer_source") or log_patch.answer_source,
            system_name=state.get("system_name") or log_patch.system_name,
            module_name=state.get("module_name") or log_patch.module_name,
            answer=state.get("answer") or "",
            fallback_reason=state.get("fallback_reason"),
            need_human=1 if confidence_level == "medium" else 0,
            risk_level="low",
            latency_ms=latency_ms,
            retrieval_time_ms=0,
            answer_time_ms=state.get("llm_latency_ms") or 0,
            llm_tokens=None,
            error_stage="llm_generate" if status == "llm_failed" else None,
            error_message=state.get("llm_error"),
            langsmith_trace_id=None,
        )
        created = self.question_repo.create_log(log)

        if write_unanswered:
            normalized = question[:500]
            existing = self.unanswered_repo.get_pending_by_normalized(normalized)
            if existing is None:
                from app.models.unanswered_question import UnansweredQuestion
                from datetime import datetime

                self.unanswered_repo.create(
                    UnansweredQuestion(
                        question_log_id=created.id,
                        question=sanitize_text(question, max_length=500),
                        normalized_question=normalized,
                        summary=sanitize_text(question, max_length=100),
                        system_name=log_patch.system_name or "",
                        module_name=log_patch.module_name or "",
                        tags="",
                        frequency=1,
                        status="pending",
                        last_seen_time=datetime.now(),
                    )
                )
            else:
                existing.frequency += 1
                from datetime import datetime
                existing.last_seen_time = datetime.now()
                self.session.flush()

        return created.id
