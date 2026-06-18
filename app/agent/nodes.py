"""LangGraph 问答工作流节点（阶段七）。

这个文件负责“每个流程节点具体干什么”。

和 app/agent/workflow.py 的关系：
- workflow.py 像流程图，负责定义节点顺序和分支；
- nodes.py 像每个流程图方框里的代码，负责具体处理 state。

LangGraph 节点的基本规则：
1. 每个节点函数都会收到 state 和 config；
2. state 是整个问答流程共享的字典；
3. 节点只需要返回“要更新的字段”；
4. LangGraph 会把返回字段合并回 state；
5. workflow.py 再根据 state 里的字段决定下一步走哪个节点。
"""

# 让类型标注延迟解析，减少类型在运行时提前求值带来的导入问题。
from __future__ import annotations

import time

# Any 表示“任意类型”。
# 这里节点返回的是 dict[str, Any]，意思是：
# - key 是字符串；
# - value 可以是 bool、str、list、int、None 等各种类型。
from typing import Any

# RunnableConfig 是 LangChain/LangGraph 运行时配置对象。
# 本项目把数据库 Session 放在 config["configurable"]["db"] 里传给每个节点。
from langchain_core.runnables import RunnableConfig

# SQLAlchemy 的数据库会话类型。
# 可以把 Session 理解成一次请求里用于查库、写库的数据库操作上下文。
from sqlalchemy.orm import Session

# AskState 是问答流程的共享状态结构。
# 实际运行时它表现得像一个 dict，里面保存 question、matched、answer 等字段。
from app.agent.ask_state import AskState

# 固定话术和原因常量。
# 这些文本集中放在 constants.py，避免散落在多个节点里。
from app.agent.constants import (
    EMPTY_QUESTION_REASON,
    RETRIEVAL_ERROR_ANSWER,
    RETRIEVAL_ERROR_REASON,
)

# KnowledgeRepository 用来按 card_id 回查 MySQL 里的知识卡片。
from app.repositories.knowledge_repository import KnowledgeRepository

# 下面三个 Service 才是真正的业务能力：
# - RetrievalService：负责向量检索；
# - AnswerGenerationService：负责命中后生成答案；
# - AskLogService：负责写 question_log 和 unanswered_question。
from app.services.answer_generation_service import AnswerGenerationService
from app.services.ask_log_service import AskLogService
from app.services.retrieval_service import RetrievalHit, RetrievalService
from app.services.trusted_answer_service import TrustedAnswerService

_trusted_answer_service = TrustedAnswerService()


def _get_db_session(config: RunnableConfig) -> Session:
    """从 LangGraph RunnableConfig 取出当前请求的 SQLAlchemy Session。

    语法解释：
    - 函数名前的 `_` 表示“内部辅助函数”，约定只在本文件内部使用。
    - `config.get("configurable") or {}`：
      如果 configurable 存在就用它；
      如果不存在或为空，就用空字典，避免后面 `.get("db")` 报错。

    业务解释：
    LangGraph 的 compiled graph 是全局缓存的，不能把数据库 Session 直接放进 graph。
    所以每次请求运行 graph 时，AskGraphRunner 会通过 config 注入当前请求的 Session。
    每个需要查库/写库的节点再用这个函数取出来。
    """

    configurable = config.get("configurable") or {}
    session = configurable.get("db")
    if session is None:
        # 这里抛 ValueError 是开发期保护：
        # 如果调用 graph 时忘了注入 db，节点无法查库/写库，应当立刻报错。
        raise ValueError("Graph 节点需要 configurable['db'] 注入当前请求 Session")
    return session


def _hits_from_state(state: AskState, session: Session) -> list[RetrievalHit]:
    """将 state 中的 retrieval_hits 还原为带 ORM 对象的 RetrievalHit 列表。

    为什么要“还原”？
    - retrieve_node 为了让 state 简洁，只把 card_id/title/score 放进 state；
    - generate_answer_node 真正生成答案时，需要完整的 KnowledgeCard ORM 对象；
    - 所以这里根据 card_id 再回 MySQL 查询一次卡片。

    语法解释：
    - `list[RetrievalHit]` 表示返回 RetrievalHit 列表；
    - `state.get("retrieval_hits") or []` 表示如果没有命中结果，就按空列表处理；
    - `continue` 表示跳过当前循环，继续处理下一条。
    """

    repo = KnowledgeRepository(session)
    hits: list[RetrievalHit] = []

    # retrieval_hits 是 retrieve_node 写入 state 的轻量结果：
    # [{"card_id": 1, "title": "...", "score": 0.9}, ...]
    for item in state.get("retrieval_hits") or []:
        card_id = item.get("card_id")
        if card_id is None:
            continue

        # 这里使用 get_searchable_by_id，而不是普通 get_by_id。
        # 这样能再次保证卡片仍然是：未删除、已审核通过、已启用。
        card = repo.get_searchable_by_id(int(card_id))
        if card is None:
            continue

        # 重新包装成 RetrievalHit，里面既有完整 card 对象，也有 title/score。
        hits.append(
            RetrievalHit(
                card=card,
                title=item.get("title") or card.title,
                score=float(item.get("score") or 0.0),
            )
        )
    return hits


def validate_input_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：校验问题非空；空问题不写日志并直接结束。

    输入：
    - state["question_raw"]：用户原始问题。

    输出：
    - 如果问题为空：返回 is_valid=False，workflow 会直接 END；
    - 如果问题非空：返回 is_valid=True，workflow 会继续预处理。

    语法解释：
    - `(state.get("question_raw") or "").strip()`：
      1. 先从 state 取 question_raw；
      2. 如果是 None，就用空字符串；
      3. strip() 去掉前后空格、换行。
    """

    question = (state.get("question_raw") or "").strip()
    if not question:
        # 空问题不进入知识库检索，不调用 LLM，也不写 question_log。
        # 这里返回的字段会被 LangGraph 合并进 state。
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

    # 有效问题：把清理过首尾空白的 question 写回 question_raw。
    # should_write_log=True 表示后续 write_log_node 可以写 question_log。
    return {
        "is_valid": True,
        "should_write_log": True,
        "question_raw": question,
        "route": "continue",
    }


def preprocess_question_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：填充 question_masked / rewritten_question 等字段。

    若 AskService 已做上下文增强，则保留改写后问题用于检索；
    否则 question_masked / rewritten_question 回退为原始问题。
    """

    question_raw = state.get("question_raw") or ""
    rewritten = state.get("rewritten_question") or question_raw
    return {
        "question_masked": rewritten,
        "rewritten_question": rewritten,
        "original_question": state.get("original_question") or question_raw,
        "used_context": state.get("used_context") or 0,
        "context_source": state.get("context_source"),
        "context_summary": state.get("context_summary"),
        "intent": "question",
        "user_id": state.get("user_id") or "anonymous",
        "group_id": state.get("group_id") or "demo_group",
        "source_type": state.get("source_type") or "web",
    }


def retrieve_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：调用 RetrievalService 做 Qdrant 向量检索。

    输入：
    - question_masked：预处理后的问题文本；
    - config 中的 db Session。

    输出：
    - 检索异常时：retrieval_error=True，route="error"；
    - 检索正常时：写入原始检索结果，route="ok"。

    注意：
    这个节点只负责“调用检索服务并记录原始结果”。
    至于算不算命中，由下一个 match_judge_node 负责。
    """

    # 从运行配置里取当前请求的数据库 Session。
    # RetrievalService 需要它回查 MySQL 知识卡片是否仍然可用。
    session = _get_db_session(config)
    question_masked = state.get("question_masked") or ""

    # time.perf_counter() 适合计算耗时。
    # 这里记录检索开始时间，后面用于计算 retrieval_time_ms。
    retrieval_started = time.perf_counter()
    retrieval = RetrievalService(session).retrieve(question_masked)
    retrieval_time_ms = int((time.perf_counter() - retrieval_started) * 1000)

    if retrieval.error is not None:
        log_patch = _trusted_answer_service.build_log_patch(
            confidence_level="none",
            matched=False,
            primary_source=None,
            retrieval_error=True,
        )
        return {
            "retrieval_error": True,
            "retrieval_time_ms": retrieval_time_ms,
            "matched": False,
            "similarity_score": 0.0,
            "confidence_level": log_patch.confidence_level,
            "answer_status": log_patch.answer_status,
            "answer_source": log_patch.answer_source,
            "sources": [],
            "retrieval_hits": [],
            "matched_card_ids": "",
            "fallback_reason": RETRIEVAL_ERROR_REASON,
            "error_message": retrieval.error,
            "route": "error",
        }

    # 将 RetrievalHit 对象转换为普通 dict，附带系统/模块供可信回答使用。
    hits_dicts = [
        {
            "card_id": hit.card.id,
            "title": hit.title,
            "score": hit.score,
            "system_name": hit.card.system_name,
            "module_name": hit.card.module_name,
        }
        for hit in retrieval.hits
    ]
    confidence_level = retrieval.confidence_level or "none"
    primary = _trusted_answer_service.get_primary_source(
        hit_dicts=hits_dicts,
        score=float(retrieval.similarity_score or 0.0),
        confidence_level=confidence_level,
    )
    return {
        "retrieval_error": False,
        "retrieval_time_ms": retrieval_time_ms,
        "_raw_matched": retrieval.matched,
        "_raw_fallback_reason": retrieval.fallback_reason,
        "_raw_similarity_score": retrieval.similarity_score,
        "confidence_level": confidence_level,
        "primary_matched_card_id": primary.card_id if primary else None,
        "primary_matched_card_title": primary.title if primary else None,
        "system_name": primary.system_name if primary else None,
        "module_name": primary.module_name if primary else None,
        "retrieval_hits": hits_dicts,
        "route": "ok",
    }


def match_judge_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：根据检索原始结果写入 matched、sources、similarity_score。

    输入：
    - retrieve_node 写入的 `_raw_matched`、`_raw_similarity_score`、`retrieval_hits`。

    输出：
    - matched=True 时，准备 sources、matched_card_ids；
    - matched=False 时，清空 sources，并保留未命中原因。

    业务解释：
    这个节点是“分岔口”。
    workflow.py 会根据这里返回的 route 决定：
    - route="matched" -> generate_answer_node；
    - route="miss" -> handle_miss_node。
    """

    # bool(...) / float(...) 是类型兜底，确保后续字段格式稳定。
    matched = bool(state.get("_raw_matched", False))
    similarity_score = float(state.get("_raw_similarity_score") or 0.0)
    fallback_reason = state.get("_raw_fallback_reason")
    hits = state.get("retrieval_hits") or []
    confidence_level = state.get("confidence_level") or "none"
    primary = _trusted_answer_service.get_primary_source(
        hit_dicts=hits,
        score=similarity_score,
        confidence_level=confidence_level,
    )

    if matched:
        sources = [
            {"card_id": int(h["card_id"]), "title": h.get("title") or "", "score": float(h.get("score") or 0.0)}
            for h in hits
        ]
        matched_card_ids = ",".join(str(h["card_id"]) for h in hits)
        log_patch = _trusted_answer_service.build_log_patch(
            confidence_level=confidence_level,
            matched=True,
            primary_source=primary,
        )
        return {
            "matched": True,
            "sources": sources,
            "matched_card_ids": matched_card_ids,
            "similarity_score": similarity_score,
            "confidence_level": log_patch.confidence_level,
            "primary_matched_card_id": log_patch.primary_matched_card_id,
            "primary_matched_card_title": log_patch.primary_matched_card_title,
            "answer_status": log_patch.answer_status,
            "answer_source": log_patch.answer_source,
            "system_name": log_patch.system_name,
            "module_name": log_patch.module_name,
            "fallback_reason": None,
            "route": "matched",
        }

    log_patch = _trusted_answer_service.build_log_patch(
        confidence_level=confidence_level,
        matched=False,
        primary_source=primary,
    )
    return {
        "matched": False,
        "sources": [],
        "matched_card_ids": "",
        "similarity_score": similarity_score,
        "confidence_level": log_patch.confidence_level,
        "primary_matched_card_id": log_patch.primary_matched_card_id,
        "primary_matched_card_title": log_patch.primary_matched_card_title,
        "answer_status": log_patch.answer_status,
        "answer_source": log_patch.answer_source,
        "system_name": log_patch.system_name,
        "module_name": log_patch.module_name,
        "fallback_reason": fallback_reason or "向量检索未命中",
        "route": "miss",
    }


def generate_answer_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：命中后调用 AnswerGenerationService 生成 LLM 答案。

    只有 matched=True 的分支才会进入这里。

    输入：
    - question_masked：用户问题；
    - retrieval_hits：命中的知识卡片 ID/title/score。

    输出：
    - answer：最终回答正文；
    - llm_tokens：模型消耗 token；
    - answer_time_ms：答案生成耗时；
    - fallback_reason / need_human / risk_level：降级和风险信息。

    业务解释：
    LLM 不是凭空回答，而是基于命中的知识卡片组织回答。
    """

    session = _get_db_session(config)
    question_masked = state.get("question_masked") or ""

    # retrieval_hits 在 state 里只是轻量 dict。
    # 生成答案前，需要重新查 MySQL，恢复成带完整 KnowledgeCard 的 RetrievalHit。
    hits = _hits_from_state(state, session)
    confidence_level = state.get("confidence_level") or "none"
    primary = _trusted_answer_service.get_primary_source(hits=hits, confidence_level=confidence_level)

    generated = AnswerGenerationService().generate(question=question_masked, hits=hits)

    if generated.error_stage:
        log_patch = _trusted_answer_service.build_log_patch(
            confidence_level=confidence_level,
            matched=True,
            primary_source=primary,
            llm_failed=True,
        )
        return {
            "answer": generated.answer,
            "llm_tokens": generated.llm_tokens,
            "answer_time_ms": generated.answer_time_ms,
            "fallback_reason": generated.fallback_reason,
            "need_human": True,
            "risk_level": generated.risk_level,
            "error_stage": generated.error_stage,
            "error_message": generated.error_message,
            "confidence_level": log_patch.confidence_level,
            "answer_status": log_patch.answer_status,
            "answer_source": log_patch.answer_source,
        }

    trusted_answer = _trusted_answer_service.build_trusted_answer(
        raw_answer=generated.answer,
        confidence_level=confidence_level,
        primary_source=primary,
        matched=True,
    )
    need_human = confidence_level == "medium" or generated.need_human

    return {
        "answer": trusted_answer,
        "llm_tokens": generated.llm_tokens,
        "answer_time_ms": generated.answer_time_ms,
        "fallback_reason": generated.fallback_reason,
        "need_human": need_human,
        "risk_level": generated.risk_level,
        "error_stage": generated.error_stage,
        "error_message": generated.error_message,
    }


def handle_miss_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：未命中时返回固定 FALLBACK_ANSWER，不调用 LLM。

    为什么未命中不调用 LLM？
    因为知识库没有可靠依据时，让模型硬答容易产生幻觉。
    MVP 的策略是：保守回复 + 记录未命中问题，后续由人工沉淀知识卡片。
    """

    trusted_answer = _trusted_answer_service.build_trusted_answer(
        raw_answer="",
        confidence_level=state.get("confidence_level") or "low",
        primary_source=None,
        matched=False,
    )
    return {
        "answer": trusted_answer,
        "need_human": False,
        "risk_level": "low",
        "llm_tokens": None,
        "answer_time_ms": 0,
        "error_stage": None,
        "error_message": None,
    }


def error_fallback_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：检索异常时的固定兜底回答。

    这个节点处理的是“系统异常”，不是“知识库未命中”。

    举例：
    - Qdrant 本地向量库无法访问；
    - 向量检索过程抛异常；
    - RetrievalService 返回 error。

    业务策略：
    - 告诉用户知识库检索暂不可用；
    - need_human=True，建议人工处理；
    - risk_level="medium"，表示风险比普通未命中更高。
    """

    log_patch = _trusted_answer_service.build_log_patch(
        confidence_level="none",
        matched=False,
        primary_source=None,
        retrieval_error=True,
    )
    return {
        "answer": RETRIEVAL_ERROR_ANSWER,
        "matched": False,
        "sources": [],
        "matched_card_ids": "",
        "similarity_score": 0.0,
        "confidence_level": log_patch.confidence_level,
        "answer_status": log_patch.answer_status,
        "answer_source": log_patch.answer_source,
        "fallback_reason": RETRIEVAL_ERROR_REASON,
        "need_human": True,
        "risk_level": "medium",
        "llm_tokens": None,
        "answer_time_ms": 0,
        "error_stage": None,
    }


def write_log_node(state: AskState, config: RunnableConfig) -> dict[str, Any]:
    """节点：写入 question_log 与 unanswered_question，返回 question_log_id。

    这是流程的最后一个业务节点。

    输入：
    - 前面所有节点合并后的 state。

    输出：
    - question_log_id：本次提问日志 ID；
    - latency_ms：整条问答链路耗时。

    业务解释：
    AskLogService 会做两件事：
    1. 有效问题写 question_log；
    2. 如果未命中且不是检索异常，写入或更新 unanswered_question。
    """

    session = _get_db_session(config)

    # started_at 是 AskService 构造初始 state 时写入的开始时间。
    # 如果极端情况下没有 started_at，就用当前时间兜底。
    started_at = state.get("started_at") or time.perf_counter()
    latency_ms = int((time.perf_counter() - started_at) * 1000)

    # 真正的落库逻辑在 AskLogService 中。
    # 节点这里只负责调用它，并把 question_log_id 写回 state。
    question_log_id = AskLogService(session).write_log(state)
    return {
        "question_log_id": question_log_id,
        "latency_ms": latency_ms,
    }
