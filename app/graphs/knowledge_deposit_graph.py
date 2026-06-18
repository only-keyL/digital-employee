"""KnowledgeDepositGraph：指令式知识沉淀 LangGraph 工作流。"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import lru_cache
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.core.desensitize import sanitize_text
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.knowledge_contribution_repository import KnowledgeContributionRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.wecom_message_schema import WeComMessage
from app.services.duplicate_check_service import DuplicateCheckError, DuplicateCheckService
from app.services.knowledge_card_parser import KnowledgeCardParser
from app.services.knowledge_content import card_to_content_dict, compute_content_hash
from app.services.knowledge_deposit_check_service import KnowledgeDepositCheckService

logger = logging.getLogger(__name__)


class KnowledgeDepositState(TypedDict, total=False):
    contribution_id: str
    graph_run_id: str
    message: dict
    raw_content: str
    parsed_card: dict
    missing_fields: list[str]
    completeness_score: float
    ai_check_result: dict
    mysql_duplicate_result: dict
    qdrant_duplicate_result: dict
    risk_result: dict
    status: str
    reply: str
    knowledge_card_id: int | None
    deposit_duplicate_check: dict
    deposit_pre_check_hint: bool
    errors: list[str]
    started_at: float
    exit_session: bool


class KnowledgeDepositGraphRunner:
    """KnowledgeDepositGraph 执行器。"""

    TRACE_NAME = "KnowledgeDepositGraph"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.contrib_repo = KnowledgeContributionRepository(session)
        self.knowledge_repo = KnowledgeRepository(session)
        self.parser = KnowledgeCardParser()
        self.check_service = KnowledgeDepositCheckService(session)
        self.graph = get_compiled_knowledge_deposit_graph()

    async def run(self, message: WeComMessage) -> KnowledgeDepositState:
        state: KnowledgeDepositState = {
            "graph_run_id": str(uuid.uuid4()),
            "message": message.model_dump(),
            "raw_content": message.content,
            "started_at": time.perf_counter(),
            "errors": [],
            "exit_session": False,
        }
        config = {"configurable": {"runner": self}}
        if self.settings.is_langsmith_enabled:
            return await self._run_with_langsmith(state, config)
        return await self.graph.ainvoke(state, config)

    async def _run_with_langsmith(self, state: KnowledgeDepositState, config: dict) -> KnowledgeDepositState:
        from langsmith.run_trees import RunTree

        msg = state.get("message") or {}
        run = RunTree(
            name=self.TRACE_NAME,
            run_type="chain",
            inputs={"content_preview": sanitize_text(state.get("raw_content", ""), max_length=120)},
            project_name=self.settings.langsmith_project,
            extra={"metadata": {"module": "digital_employee", "stage": "stage4", "user_id": msg.get("user_id")}},
        )
        try:
            result = await self.graph.ainvoke(state, config)
            run.end(
                outputs={
                    "status": result.get("status"),
                    "contribution_id": result.get("contribution_id"),
                    "knowledge_card_id": result.get("knowledge_card_id"),
                    "reply_preview": sanitize_text(result.get("reply", ""), max_length=120),
                }
            )
            run.post()
            return result
        except Exception as exc:
            run.end(error=str(exc))
            run.post()
            raise


def build_knowledge_deposit_graph() -> StateGraph:
    graph = StateGraph(KnowledgeDepositState)
    graph.add_node("create_contribution", create_contribution)
    graph.add_node("parse_card", parse_card)
    graph.add_node("check_completeness", check_completeness)
    graph.add_node("ai_quality_check", ai_quality_check)
    graph.add_node("duplicate_check", duplicate_check)
    graph.add_node("risk_check", risk_check)
    graph.add_node("create_pending_knowledge", create_pending_knowledge)
    graph.add_node("persist_and_reply", persist_and_reply)

    graph.add_edge(START, "create_contribution")
    graph.add_edge("create_contribution", "parse_card")
    graph.add_edge("parse_card", "check_completeness")
    graph.add_conditional_edges(
        "check_completeness",
        route_after_completeness,
        {"continue": "ai_quality_check", "reply": "persist_and_reply"},
    )
    graph.add_conditional_edges(
        "ai_quality_check",
        route_after_ai,
        {"continue": "duplicate_check", "reply": "persist_and_reply"},
    )
    graph.add_conditional_edges(
        "duplicate_check",
        route_after_duplicate,
        {"continue": "risk_check", "reply": "persist_and_reply"},
    )
    graph.add_conditional_edges(
        "risk_check",
        route_after_risk,
        {"continue": "create_pending_knowledge", "reply": "persist_and_reply"},
    )
    graph.add_edge("create_pending_knowledge", "persist_and_reply")
    graph.add_edge("persist_and_reply", END)
    return graph


@lru_cache
def get_compiled_knowledge_deposit_graph():
    return build_knowledge_deposit_graph().compile()


def _runner(config) -> KnowledgeDepositGraphRunner:
    return config["configurable"]["runner"]


async def create_contribution(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    """创建投稿记录，status=checking。"""
    runner = _runner(config)
    msg_data = state.get("message") or {}
    contribution_id = str(uuid.uuid4())
    record = KnowledgeContribution(
        contribution_id=contribution_id,
        source=msg_data.get("source") or "mock_wecom",
        message_id=msg_data.get("message_id"),
        group_id=msg_data.get("group_id"),
        user_id=msg_data.get("user_id") or "unknown",
        user_name=msg_data.get("user_name"),
        raw_content=state.get("raw_content") or "",
        status="checking",
        graph_run_id=state.get("graph_run_id"),
    )
    runner.contrib_repo.create(record)
    state["contribution_id"] = contribution_id
    return state


async def parse_card(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    """解析结构化知识卡片文本。"""
    runner = _runner(config)
    result = runner.parser.parse(state.get("raw_content") or "")
    state["parsed_card"] = result.parsed_card
    state["missing_fields"] = result.missing_fields
    return state


async def check_completeness(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    runner = _runner(config)
    result = runner.check_service.check_completeness(
        state.get("parsed_card") or {},
        state.get("missing_fields") or [],
    )
    state["completeness_score"] = result.score
    if not result.passed:
        state["status"] = "invalid"
        missing = "、".join(result.missing_fields)
        state["reply"] = f"知识卡片字段不完整，请补充：{missing}。可发送【模板】查看格式。"
        state["exit_session"] = False
    return state


def route_after_completeness(state: KnowledgeDepositState) -> Literal["continue", "reply"]:
    return "reply" if state.get("status") == "invalid" else "continue"


async def ai_quality_check(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    runner = _runner(config)
    result = await runner.check_service.ai_quality_check(state.get("parsed_card") or {})
    state["ai_check_result"] = {
        "passed": result.passed,
        "score": result.score,
        "missing": result.missing,
        "suggestions": result.suggestions,
        "reason": result.reason,
        "error": result.error,
    }
    if result.error:
        state["status"] = "failed"
        state["reply"] = "AI 质量检查暂时不可用，请稍后重试。"
        state["exit_session"] = False
    elif not result.passed:
        state["status"] = "invalid"
        reason = result.reason or "内容质量未达标"
        state["reply"] = f"知识卡片未通过 AI 质量检查：{reason}"
        state["exit_session"] = True
    return state


def route_after_ai(state: KnowledgeDepositState) -> Literal["continue", "reply"]:
    if state.get("status") in {"invalid", "failed"}:
        return "reply"
    return "continue"


async def duplicate_check(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    """MySQL + Qdrant 轻量预检：仅记录提示信息，不阻断后续 DuplicateCheckService 正式检测。"""
    runner = _runner(config)
    parsed = state.get("parsed_card") or {}
    mysql_result = runner.check_service.check_mysql_duplicate(parsed)
    qdrant_result = await runner.check_service.check_qdrant_duplicate(parsed)
    state["mysql_duplicate_result"] = {
        "duplicate_suspected": mysql_result.duplicate_suspected,
        "matches": mysql_result.mysql_matches,
        "pre_check_only": True,
    }
    state["qdrant_duplicate_result"] = {
        "duplicate_suspected": qdrant_result.duplicate_suspected,
        "duplicate_possible": qdrant_result.duplicate_possible,
        "top_score": qdrant_result.top_score,
        "matches": qdrant_result.qdrant_matches,
        "skipped": qdrant_result.skipped,
        "message": qdrant_result.message,
        "pre_check_only": True,
    }

    # 旧预检结果只写入 state 供 contribution 参考，最终重复治理统一在 create_pending_knowledge 由 DuplicateCheckService 完成
    strong_dup = mysql_result.duplicate_suspected or qdrant_result.duplicate_suspected
    if strong_dup:
        state["deposit_pre_check_hint"] = True
    return state


def route_after_duplicate(state: KnowledgeDepositState) -> Literal["continue", "reply"]:
    # 方案 A：旧 duplicate_check 不再阻断，始终进入 risk_check → create_pending_knowledge
    return "continue"


async def risk_check(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    runner = _runner(config)
    result = runner.check_service.check_risk(
        state.get("parsed_card") or {},
        state.get("raw_content") or "",
    )
    state["risk_result"] = {
        "risk_level": result.risk_level,
        "hits": result.hits,
        "blocked": result.blocked,
        "message": result.message,
    }
    if result.risk_level == "high":
        state["status"] = "risk_blocked"
        state["reply"] = result.message
        state["exit_session"] = True
    elif result.risk_level == "medium":
        state["status"] = "invalid"
        state["reply"] = result.message
        state["exit_session"] = True
    return state


def route_after_risk(state: KnowledgeDepositState) -> Literal["continue", "reply"]:
    if state.get("status") in {"risk_blocked", "invalid"} and state.get("risk_result", {}).get("blocked"):
        return "reply"
    if state.get("status") == "risk_blocked":
        return "reply"
    return "continue"


async def create_pending_knowledge(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    """生成待审核知识卡片：先 draft 落库做重复检测，通过后改 pending。"""
    runner = _runner(config)
    parsed = state.get("parsed_card") or {}
    msg = state.get("message") or {}
    operator = msg.get("user_name") or msg.get("user_id") or "wecom_user"

    # 先以 draft 写入并获得 ID，便于 duplicate_check_log 关联 source_card_id
    card = KnowledgeCard(
        title=parsed.get("title", "").strip(),
        question=parsed.get("question", "").strip(),
        answer=parsed.get("answer", "").strip(),
        system_name=parsed.get("system_name"),
        module_name=parsed.get("module_name"),
        tags=parsed.get("tags"),
        scene=parsed.get("scene"),
        reason_analysis=parsed.get("reason_analysis"),
        troubleshooting_steps=parsed.get("troubleshooting_steps"),
        solution=parsed.get("solution"),
        risk_notice=parsed.get("risk_notice"),
        source_group=parsed.get("source_group") or msg.get("group_id"),
        source_user=parsed.get("source_user") or operator,
        audit_status="draft",
        enabled=0,
        deleted=0,
        vector_status="waiting_review",
        version=1,
        create_user=operator,
        update_user=operator,
    )
    card.content_hash = compute_content_hash(card_to_content_dict(card))
    runner.knowledge_repo.add(card)
    runner.session.flush()

    # 进入 pending 前执行 DuplicateCheckService，只预警不阻断；失败则不进入 pending
    try:
        duplicate_result = await DuplicateCheckService(runner.session).check_card_object_async(
            card,
            operator_user=operator,
            source_type="user_deposit",
        )
    except DuplicateCheckError as exc:
        runner.session.delete(card)
        runner.session.flush()
        state["status"] = "duplicate_check_failed"
        state["reply"] = f"重复检测失败，暂未生成待审核知识卡片：{exc.message}"
        state["exit_session"] = True
        logger.warning("企微沉淀重复检测失败 card_id=%s error=%s", card.id, exc.message)
        return state

    # 检测成功：即使 high_duplicate 也只预警，卡片仍进入 pending
    card.audit_status = "pending"
    card.update_user = operator
    runner.session.flush()

    state["knowledge_card_id"] = card.id
    state["deposit_duplicate_check"] = duplicate_result.model_dump()
    state["status"] = "pending_card_created"

    duplicate_note = ""
    if duplicate_result.has_high_risk_duplicate or duplicate_result.highest_level in {
        "high_duplicate",
        "suspected_duplicate",
    }:
        duplicate_note = "发现相似知识，审核时请重点确认。"

    qdrant_note = ""
    qdrant_dup = state.get("qdrant_duplicate_result") or {}
    if qdrant_dup.get("duplicate_possible"):
        qdrant_note = "（系统检测到轻度语义相似，已进入人工审核队列）"

    state["reply"] = (
        f"知识投稿已受理，已生成待审核知识卡片（ID={card.id}）。"
        f"{duplicate_note}{qdrant_note}"
        "管理员审核通过后才会进入知识库与向量同步。"
    )
    state["exit_session"] = True
    return state


async def persist_and_reply(state: KnowledgeDepositState, config) -> KnowledgeDepositState:
    """落库 contribution 并生成最终回复。"""
    runner = _runner(config)
    contrib = runner.contrib_repo.get_by_contribution_id(state["contribution_id"])
    if contrib is None:
        return state

    parsed = state.get("parsed_card") or {}
    contrib.parsed_card_json = json.dumps(parsed, ensure_ascii=False)
    contrib.completeness_score = state.get("completeness_score")
    contrib.missing_fields_json = json.dumps(state.get("missing_fields") or [], ensure_ascii=False)
    contrib.status = state.get("status") or "failed"
    contrib.duplicate_suspected = bool(
        state.get("deposit_pre_check_hint")
        or (state.get("deposit_duplicate_check") or {}).get("has_high_risk_duplicate")
        or (state.get("deposit_duplicate_check") or {}).get("highest_level")
        in {"high_duplicate", "suspected_duplicate"}
    )
    contrib.duplicate_result_json = json.dumps(
        {
            "mysql": state.get("mysql_duplicate_result"),
            "qdrant": state.get("qdrant_duplicate_result"),
            "duplicate_check_service": state.get("deposit_duplicate_check"),
        },
        ensure_ascii=False,
    )
    risk = state.get("risk_result") or {}
    contrib.risk_level = risk.get("risk_level") or "none"
    contrib.risk_result_json = json.dumps(risk, ensure_ascii=False)
    contrib.knowledge_card_id = state.get("knowledge_card_id")
    if state.get("ai_check_result"):
        contrib.reject_reason = (state.get("ai_check_result") or {}).get("reason")
    if contrib.status == "invalid" and state.get("missing_fields"):
        contrib.reject_reason = "字段不完整"

    runner.contrib_repo.save()
    runner.session.commit()
    return state
