"""AskGraphV2：Stage3 RAG 问答 LangGraph 工作流。"""

from __future__ import annotations

import logging
import time
import uuid
from functools import lru_cache
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.desensitize import sanitize_text
from app.rag.rag_retrieval_service import RagRetrievalResult, RagRetrievalService
from app.services.ask_run_log_service import AskRunLogService
from app.services.rag_answer_service import RagAnswerService

logger = logging.getLogger(__name__)

_LOW_CONFIDENCE_ANSWER = "当前知识库没有足够依据，已记录为未命中问题。"
_LLM_FALLBACK_ANSWER = "当前模型服务暂时不可用，已记录问题，请稍后重试或联系管理员。"


class AskGraphV2State(TypedDict, total=False):
    run_id: str
    question: str
    normalized_question: str
    source: str
    user_id: str | None
    retrieval: RagRetrievalResult | None
    contexts: list[Any]
    top_score: float
    confidence_level: str
    answer: str
    status: str
    fallback_reason: str | None
    errors: list[str]
    started_at: float
    llm_status: str
    llm_error: str | None
    llm_latency_ms: int
    llm_prompt: str


class AskGraphV2Runner:
    """AskGraphV2 执行器：协调 RAG 检索、生成与日志落库。"""

    TRACE_NAME = "AskGraphV2_RAG"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.retrieval_service = RagRetrievalService(session)
        self.answer_service = RagAnswerService()
        self.log_service = AskRunLogService(session)
        self.graph = get_compiled_ask_graph_v2()

    async def run(
        self,
        *,
        question: str,
        user_id: str | None = None,
        source: str = "api_ask_v2",
    ) -> AskGraphV2State:
        state: AskGraphV2State = {
            "run_id": str(uuid.uuid4()),
            "question": question,
            "source": source,
            "user_id": user_id,
            "started_at": time.perf_counter(),
            "errors": [],
        }
        config = {"configurable": {"runner": self}}
        if self._langsmith_enabled():
            return await self._run_with_langsmith(state, config)
        return await self.graph.ainvoke(state, config)

    async def _run_with_langsmith(self, state: AskGraphV2State, config: dict) -> AskGraphV2State:
        from langsmith.run_trees import RunTree

        metadata = {
            "module": "digital_employee",
            "stage": "stage3",
            "env": self.settings.app_env,
            "source": state.get("source"),
        }
        run = RunTree(
            name=self.TRACE_NAME,
            run_type="chain",
            inputs={"question_preview": sanitize_text(state.get("question", ""), max_length=120)},
            project_name=self.settings.langsmith_project,
            extra={"metadata": metadata},
        )
        try:
            result = await self.graph.ainvoke(state, config)
            run.end(
                outputs={
                    "status": result.get("status"),
                    "confidence_level": result.get("confidence_level"),
                    "top_score": result.get("top_score"),
                    "answer_preview": sanitize_text(result.get("answer", ""), max_length=120),
                }
            )
            run.post()
            return result
        except Exception as exc:
            run.end(error=str(exc))
            run.post()
            raise

    def _langsmith_enabled(self) -> bool:
        return self.settings.is_langsmith_enabled


def build_ask_graph_v2() -> StateGraph:
    graph = StateGraph(AskGraphV2State)
    graph.add_node("normalize_question", normalize_question)
    graph.add_node("retrieve_knowledge", retrieve_knowledge)
    graph.add_node("judge_confidence", judge_confidence)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("risk_check", risk_check)
    graph.add_node("fallback_answer", fallback_answer)
    graph.add_node("persist_logs", persist_logs)

    graph.add_edge(START, "normalize_question")
    graph.add_edge("normalize_question", "retrieve_knowledge")
    graph.add_edge("retrieve_knowledge", "judge_confidence")
    graph.add_conditional_edges(
        "judge_confidence",
        route_after_judge,
        {"generate": "generate_answer", "fallback": "fallback_answer"},
    )
    graph.add_conditional_edges(
        "generate_answer",
        route_after_generate,
        {"risk": "risk_check", "fallback": "fallback_answer"},
    )
    graph.add_edge("risk_check", "persist_logs")
    graph.add_edge("fallback_answer", "persist_logs")
    graph.add_edge("persist_logs", END)
    return graph


@lru_cache
def get_compiled_ask_graph_v2():
    return build_ask_graph_v2().compile()


def _runner(config) -> AskGraphV2Runner:
    return config["configurable"]["runner"]


async def normalize_question(state: AskGraphV2State, config) -> AskGraphV2State:
    question = (state.get("question") or "").strip()
    runner = _runner(config)
    runner.log_service.create_run(
        run_id=state["run_id"],
        question=state.get("question") or "",
        normalized_question=question,
        source=state.get("source") or "api_ask_v2",
        user_id=state.get("user_id"),
    )
    if not question:
        state["errors"] = (state.get("errors") or []) + ["问题不能为空"]
        state["status"] = "failed"
        state["confidence_level"] = "none"
        state["fallback_reason"] = "empty_question"
        state["answer"] = _LOW_CONFIDENCE_ANSWER
        return state
    state["normalized_question"] = question
    return state


async def retrieve_knowledge(state: AskGraphV2State, config) -> AskGraphV2State:
    if state.get("status") == "failed":
        return state
    runner = _runner(config)
    retrieval = await runner.retrieval_service.retrieve(state["normalized_question"])
    state["retrieval"] = retrieval
    state["contexts"] = retrieval.contexts
    state["top_score"] = retrieval.top_score
    state["confidence_level"] = retrieval.confidence_level
    runner.log_service.save_retrieval_logs(state["run_id"], retrieval)
    return state


async def judge_confidence(state: AskGraphV2State, config) -> AskGraphV2State:
    retrieval = state.get("retrieval")
    if retrieval is None or not retrieval.matched:
        state["status"] = "low_confidence"
        state["fallback_reason"] = retrieval.fallback_reason if retrieval else "retrieval_failed"
        state["confidence_level"] = retrieval.confidence_level if retrieval else "low"
    return state


def route_after_judge(state: AskGraphV2State) -> Literal["generate", "fallback"]:
    if state.get("status") in {"failed", "low_confidence"}:
        return "fallback"
    if state.get("confidence_level") == "low":
        return "fallback"
    if state.get("confidence_level") in {"high", "medium"}:
        return "generate"
    return "fallback"


async def generate_answer(state: AskGraphV2State, config) -> AskGraphV2State:
    runner = _runner(config)
    contexts = state.get("contexts") or []
    result = await runner.answer_service.generate(state["normalized_question"], contexts)
    state["llm_status"] = result.status
    state["llm_error"] = result.error_message
    state["llm_latency_ms"] = result.latency_ms
    state["llm_prompt"] = result.prompt
    runner.log_service.save_llm_log(
        run_id=state["run_id"],
        provider=result.provider,
        model=result.model,
        status=result.status,
        prompt=result.prompt,
        response=result.answer,
        error_code=result.error_code,
        error_message=result.error_message,
        latency_ms=result.latency_ms,
    )
    if result.status != "success":
        state["status"] = "llm_failed"
        state["fallback_reason"] = "llm_failed"
        state["answer"] = result.answer
        return state
    state["status"] = "success"
    state["answer"] = result.answer
    return state


def route_after_generate(state: AskGraphV2State) -> Literal["risk", "fallback"]:
    if state.get("status") == "llm_failed":
        return "fallback"
    return "risk"


async def risk_check(state: AskGraphV2State, config) -> AskGraphV2State:
    answer = state.get("answer") or ""
    if any(k in answer for k in ("删除", "drop", "truncate", "root")):
        state["answer"] = answer + "\n\n【风险提示】涉及敏感操作，请先备份并在测试环境验证。"
    return state


async def fallback_answer(state: AskGraphV2State, config) -> AskGraphV2State:
    if state.get("status") == "llm_failed":
        state["answer"] = state.get("answer") or _LLM_FALLBACK_ANSWER
        return state
    state["status"] = "low_confidence"
    state["answer"] = _LOW_CONFIDENCE_ANSWER
    if not state.get("fallback_reason"):
        state["fallback_reason"] = "retrieval_score_below_threshold"
    return state


async def persist_logs(state: AskGraphV2State, config) -> AskGraphV2State:
    runner = _runner(config)
    started = state.get("started_at") or time.perf_counter()
    latency_ms = int((time.perf_counter() - started) * 1000)
    run = runner.log_service.ask_run_repo.get_by_run_id(state["run_id"])
    if run is None:
        return state
    write_unanswered = state.get("status") in {"low_confidence", "llm_failed"}
    runner.log_service.finalize_run(
        run,
        answer=state.get("answer"),
        status=state.get("status") or "failed",
        confidence_level=state.get("confidence_level") or "none",
        top_score=state.get("top_score"),
        fallback_reason=state.get("fallback_reason"),
        latency_ms=latency_ms,
        write_unanswered=write_unanswered,
    )
    runner.session.commit()
    return state
