"""LangGraph 问答工作流定义（阶段七）。"""

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
    """校验后路由：空问题直接 END，否则继续预处理。"""
    if not state.get("is_valid", False):
        return ROUTE_END
    return ROUTE_CONTINUE


def route_after_retrieve(state: AskState) -> str:
    """检索后路由：异常走 error_fallback，否则 match_judge。"""
    if state.get("retrieval_error", False):
        return ROUTE_ERROR
    return ROUTE_OK


def route_after_match(state: AskState) -> str:
    """命中判断后路由：命中 generate_answer，未命中 handle_miss。"""
    if state.get("matched", False):
        return ROUTE_MATCHED
    return ROUTE_MISS


def build_ask_workflow():
    """构建并编译 8 节点问答 StateGraph。"""
    graph = StateGraph(AskState)

    graph.add_node("validate_input", validate_input_node)  # 校验输入
    graph.add_node("preprocess_question", preprocess_question_node)  # 预处理问题
    graph.add_node("retrieve", retrieve_node)  # 向量检索
    graph.add_node("match_judge", match_judge_node)  # 命中判定
    graph.add_node("generate_answer", generate_answer_node)  # LLM 生成答案
    graph.add_node("handle_miss", handle_miss_node)  # 未命中固定话术
    graph.add_node("error_fallback", error_fallback_node)  # 检索异常兜底
    graph.add_node("write_log", write_log_node)  # 写 question_log / 未命中表

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
    """获取进程内缓存的 compiled graph（不含 Session）。"""
    return build_ask_workflow()
