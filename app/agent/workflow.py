"""LangGraph workflow definition for /api/ask (Phase 7)."""

from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.ask_state import AskState
from app.agent.constants import (
    ROUTE_CONTINUE,
    ROUTE_END,
    ROUTE_ERROR,
    ROUTE_MATCHED,
    ROUTE_MISS,
    ROUTE_OK,
)
from app.agent.nodes import (
    error_fallback_node,
    generate_answer_node,
    handle_miss_node,
    match_judge_node,
    preprocess_question_node,
    retrieve_node,
    validate_input_node,
    write_log_node,
)


def route_after_validate(state: AskState) -> str:
    if not state.get("is_valid", False):
        return ROUTE_END
    return ROUTE_CONTINUE


def route_after_retrieve(state: AskState) -> str:
    if state.get("retrieval_error", False):
        return ROUTE_ERROR
    return ROUTE_OK


def route_after_match(state: AskState) -> str:
    if state.get("matched", False):
        return ROUTE_MATCHED
    return ROUTE_MISS


def build_ask_workflow():
    graph = StateGraph(AskState)

    graph.add_node("validate_input", validate_input_node)
    graph.add_node("preprocess_question", preprocess_question_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("match_judge", match_judge_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("handle_miss", handle_miss_node)
    graph.add_node("error_fallback", error_fallback_node)
    graph.add_node("write_log", write_log_node)

    graph.add_edge(START, "validate_input")
    graph.add_conditional_edges(
        "validate_input",
        route_after_validate,
        {ROUTE_END: END, ROUTE_CONTINUE: "preprocess_question"},
    )
    graph.add_edge("preprocess_question", "retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {ROUTE_ERROR: "error_fallback", ROUTE_OK: "match_judge"},
    )
    graph.add_conditional_edges(
        "match_judge",
        route_after_match,
        {ROUTE_MATCHED: "generate_answer", ROUTE_MISS: "handle_miss"},
    )
    graph.add_edge("generate_answer", "write_log")
    graph.add_edge("handle_miss", "write_log")
    graph.add_edge("error_fallback", "write_log")
    graph.add_edge("write_log", END)

    return graph.compile()


@lru_cache(maxsize=1)
def get_compiled_ask_graph():
    """Process-wide cached compiled graph without Session."""
    return build_ask_workflow()
