"""Stage3 问答日志落库：ask_run / retrieval_log / llm_call_log。"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from app.core.desensitize import sanitize_text
from app.models.ask_run import AskRun
from app.models.llm_call_log import LlmCallLog
from app.models.retrieval_log import RetrievalLog
from app.rag.confidence import classify_confidence
from app.rag.rag_retrieval_service import RagRetrievalResult, RagRetrievalService
from app.repositories.stage3_repository import AskRunRepository, LlmCallLogRepository, RetrievalLogRepository
from app.repositories.unanswered_repository import UnansweredRepository


class AskRunLogService:
    """AskGraphV2 运行过程的结构化日志写入。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.ask_run_repo = AskRunRepository(session)
        self.retrieval_repo = RetrievalLogRepository(session)
        self.llm_repo = LlmCallLogRepository(session)
        self.unanswered_repo = UnansweredRepository(session)

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
