"""问答服务：/api/ask 入口，负责 state 构建与响应映射。"""

from __future__ import annotations

import asyncio
import time

from sqlalchemy.orm import Session

from app.agent.ask_state import AskState
from app.agent.graph_runner import AskGraphRunner
from app.schemas.ask_schema import AskRequest, AskResponse, AskSourceItem
from app.schemas.context_schema import ContextEnhanceResult
from app.services.context_enhance_service import ContextEnhanceService
from app.services.conversation_context_service import ConversationContextService


class AskService:
    """问答业务入口，调用 LangGraph 完成检索、生成与落库。"""

    def __init__(self, session: Session) -> None:
        self.session = session  # 当前请求的数据库 Session

    def ask(self, payload: AskRequest) -> AskResponse:
        """执行一次完整问答流程。"""
        enhance_result = ContextEnhanceService(self.session).enhance_question(
            question=payload.question or "",
            user_id=payload.user_id or "anonymous",
            group_id=payload.group_id,
        )
        initial_state = self._build_initial_state(payload, enhance_result)
        final_state = AskGraphRunner(self.session).run(initial_state)
        self._save_conversation_context(payload, enhance_result, final_state)
        return self._map_state_to_response(final_state)

    def _build_initial_state(self, payload: AskRequest, enhance: ContextEnhanceResult) -> AskState:
        """将 HTTP 请求体与上下文增强结果转换为 LangGraph 初始 AskState。"""
        original = enhance.original_question or (payload.question or "")
        rewritten = enhance.rewritten_question or original
        return {
            "question_raw": original,
            "original_question": original,
            "question_masked": rewritten,
            "rewritten_question": rewritten,
            "used_context": 1 if enhance.used_context else 0,
            "context_source": enhance.context_source,
            "context_summary": enhance.context_summary,
            "user_id": payload.user_id or "anonymous",
            "group_id": payload.group_id or "demo_group",
            "source_type": payload.source_type or "web",
            "started_at": time.perf_counter(),
            "is_valid": False,
            "should_write_log": False,
            "retrieval_error": False,
            "matched": False,
            "similarity_score": 0.0,
            "confidence_level": "none",
            "answer_status": "unknown",
            "answer_source": None,
            "primary_matched_card_id": None,
            "primary_matched_card_title": None,
            "system_name": None,
            "module_name": None,
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

    def _save_conversation_context(
        self,
        payload: AskRequest,
        enhance: ContextEnhanceResult,
        state: AskState,
    ) -> None:
        """问答结束后保存 Redis 短期上下文，失败不影响主流程。"""
        user_id = (payload.user_id or "").strip()
        answer = (state.get("answer") or "").strip()
        if not user_id or not answer:
            return

        svc = ConversationContextService()
        asyncio.run(
            svc.save_recent_context(
                user_id=user_id,
                group_id=payload.group_id,
                question=enhance.original_question,
                rewritten_question=enhance.rewritten_question,
                answer=answer,
                system_name=state.get("system_name"),
                module_name=state.get("module_name"),
                primary_matched_card_id=state.get("primary_matched_card_id"),
                primary_matched_card_title=state.get("primary_matched_card_title"),
                confidence_level=state.get("confidence_level"),
            )
        )

    def _map_state_to_response(self, state: AskState) -> AskResponse:
        """将 LangGraph 最终 state 映射为 /api/ask 响应结构。"""
        sources = [
            AskSourceItem(
                source_type=item.get("source_type") or "knowledge_card",
                card_id=int(item.get("card_id") or 0),
                title=item.get("title") or "",
                score=float(item.get("score") or 0.0),
                chunk_id=item.get("chunk_id"),
                doc_id=item.get("doc_id"),
                doc_name=item.get("doc_name"),
                section_path=item.get("section_path"),
                page_no=item.get("page_no"),
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
            confidence_level=state.get("confidence_level"),
            answer_status=state.get("answer_status"),
            answer_source=state.get("answer_source"),
        )
