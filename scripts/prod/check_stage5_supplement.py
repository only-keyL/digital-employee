#!/usr/bin/env python
"""Stage5 补充验收：vector_status 统一、审核幂等、RAG 检索、脱敏与页面/API 一致性。"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func, select

from app.core.desensitize import sanitize_text
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.graphs.ask_graph_v2 import AskGraphV2Runner
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.models.vector_sync_task import VectorSyncTask
from app.repositories.admin_review_repository import AdminReviewRepository
from app.schemas.admin_review_schema import (
    ContributionMarkReviewRequest,
    KnowledgeReviewActionRequest,
)
from app.schemas.wecom_message_schema import WeComMessage
from app.services.admin_review_service import AdminReviewService, AdminReviewServiceError
from app.services.knowledge_content import card_to_content_dict, compute_content_hash
from app.services.stage3_vector_sync_service import Stage3VectorSyncService
from app.wecom.command_router import CommandRouter

DEFAULT_ENV_FILE = "docs/prod/.env"
SUPPLEMENT_PREFIX = "【阶段5补充验收】"
AUDIT_USER = "stage5-supplement-check"

DUPLICATE_CARD = """标题：登录失败提示账号无权限处理办法
问题：客户登录失败并提示账号无权限时如何排查？
答案：先确认账号是否启用，再检查角色权限、组织权限和菜单权限。
系统：业务系统
模块：登录权限
标签：登录,权限,账号
场景：客户无法登录
解决方案：补充分配角色和菜单权限后，让客户重新登录验证。"""

RISK_CARD = """标题：数据库误删恢复演练记录{suffix}
问题：测试环境误执行删表脚本后应如何规范处置？
答案：立即停止写入，评估影响范围，按备份策略恢复，并在变更单中记录原因。
系统：数字员工助手
模块：数据库运维
标签：数据库,恢复,演练
场景：测试环境误操作
原因分析：误执行 destructive SQL 可能导致数据不可恢复。
排查步骤：
1. 发现异常后禁止继续执行 drop table 或 truncate table 类语句。
2. 导出错误日志与 binlog 片段供 DBA 评估影响范围。
解决方案：按备份策略回滚并在变更单记录原因与改进措施。
风险提示：生产环境禁止未经审批执行删表语句。
来源群：运维演练群
来源人：dba-drill"""

_SENSITIVE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"docs/prod/\.env", re.I),
    re.compile(r"(?i)(api[_-]?key|token|password)\s*[:=]\s*\S{8,}"),
    re.compile(r"redis://[^\"\\s]+:[^@\"\\s]+@", re.I),
)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage5 补充验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _create_pending_card(
    session,
    *,
    suffix: str,
    title: str | None = None,
    question: str | None = None,
    with_contribution: bool = True,
) -> tuple[KnowledgeCard, KnowledgeContribution | None]:
    card_title = title or f"{SUPPLEMENT_PREFIX}测试卡片{suffix}"
    card_question = question or f"{SUPPLEMENT_PREFIX}本阶段审核幂等如何验证？"
    card = KnowledgeCard(
        title=card_title,
        question=card_question,
        answer=f"{SUPPLEMENT_PREFIX}通过 check_stage5_supplement.py 自动验收。",
        system_name="数字员工助手",
        module_name="知识审核",
        tags="stage5,补充验收",
        scene="阶段5补充验收",
        solution=f"{SUPPLEMENT_PREFIX}运行补充脚本验证治理闭环边界。",
        source_group="stage5_supplement",
        source_user="supplement-script",
        audit_status="pending",
        enabled=0,
        deleted=0,
        vector_status="waiting_review",
        version=1,
        create_user=AUDIT_USER,
        update_user=AUDIT_USER,
    )
    card.content_hash = compute_content_hash(card_to_content_dict(card))
    session.add(card)
    session.flush()
    contrib = None
    if with_contribution:
        contrib = KnowledgeContribution(
            contribution_id=str(uuid.uuid4()),
            source="stage5_supplement",
            user_id=AUDIT_USER,
            user_name="supplement-script",
            raw_content=sanitize_text(card_title, max_length=200),
            status="pending_card_created",
            knowledge_card_id=card.id,
            duplicate_suspected=False,
            risk_level="none",
        )
        session.add(contrib)
    session.commit()
    session.refresh(card)
    if contrib:
        session.refresh(contrib)
    return card, contrib


def _count_tasks(session, knowledge_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(VectorSyncTask)
            .where(VectorSyncTask.knowledge_id == knowledge_id)
        )
        or 0
    )


def _scan_vector_status_in_code() -> tuple[bool, str]:
    """静态检查 knowledge_card.vector_status 是否混用 success/synced。"""
    app_dir = PROJECT_ROOT / "app"
    card_success_lines: list[str] = []
    card_synced_lines: list[str] = []
    for py in app_dir.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "vector_status" not in line:
                continue
            if re.search(r"vector_status\s*=\s*[\"']success[\"']", line):
                card_success_lines.append(f"{py.relative_to(PROJECT_ROOT)}:{i}")
            if re.search(r"vector_status\s*=\s*[\"']synced[\"']", line):
                card_synced_lines.append(f"{py.relative_to(PROJECT_ROOT)}:{i}")
    worker_src = inspect.getsource(Stage3VectorSyncService._execute_task)
    approve_src = inspect.getsource(AdminReviewService.approve_knowledge)
    ok = (
        not card_success_lines
        and "vector_status = \"pending\"" in approve_src
        and 'card.vector_status = "synced"' in worker_src
    )
    detail = (
        f"knowledge_card.vector_status=success 行数={len(card_success_lines)}；"
        f"synced 赋值处={len(card_synced_lines)}；"
        f"approve 后 pending={'是' if 'vector_status = \"pending\"' in approve_src else '否'}；"
        f"worker 成功 synced={'是' if 'card.vector_status = \"synced\"' in worker_src else '否'}"
    )
    if card_success_lines:
        detail += f"；异常行={card_success_lines[:3]}"
    return ok, detail


def check_vector_status_unified() -> CheckResult:
    ok, detail = _scan_vector_status_in_code()
    return CheckResult("1. vector_status 状态统一", ok, detail)


async def check_approve_idempotent(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    card, _ = _create_pending_card(session, suffix=f"ap-idem-{suffix}")
    svc = AdminReviewService(session)
    payload = KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER)
    r1 = svc.approve_knowledge(card.id, payload)
    session.expire_all()
    tasks_after_first = _count_tasks(session, card.id)
    try:
        svc.approve_knowledge(card.id, payload)
        second_blocked = False
    except AdminReviewServiceError:
        second_blocked = True
    session.expire_all()
    tasks_after_second = _count_tasks(session, card.id)
    approved = session.get(KnowledgeCard, card.id)
    ok = (
        r1.get("vector_sync_task_created") is True
        and tasks_after_first == 1
        and second_blocked
        and tasks_after_second == 1
        and approved is not None
        and approved.audit_status == "approved"
        and approved.vector_status == "pending"
    )
    return CheckResult(
        "2. 审核通过幂等",
        ok,
        f"首次task={tasks_after_first} 二次拦截={second_blocked} 最终task={tasks_after_second} "
        f"vector_status={approved.vector_status if approved else None}",
    )


async def check_reject_idempotent(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    card, _ = _create_pending_card(session, suffix=f"rj-idem-{suffix}")
    svc = AdminReviewService(session)
    reject_payload = KnowledgeReviewActionRequest(
        action="reject",
        audit_user=AUDIT_USER,
        audit_remark="阶段5补充验收拒绝测试",
    )
    svc.reject_knowledge(card.id, reject_payload)
    session.expire_all()
    tasks_after_reject = _count_tasks(session, card.id)
    try:
        svc.reject_knowledge(card.id, reject_payload)
        reject_twice_blocked = False
    except AdminReviewServiceError:
        reject_twice_blocked = True
    try:
        svc.approve_knowledge(
            card.id,
            KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER),
        )
        approve_after_reject_blocked = False
    except AdminReviewServiceError:
        approve_after_reject_blocked = True
    rejected = session.get(KnowledgeCard, card.id)
    ok = (
        rejected is not None
        and rejected.audit_status == "rejected"
        and tasks_after_reject == 0
        and reject_twice_blocked
        and approve_after_reject_blocked
    )
    return CheckResult(
        "3. 审核拒绝幂等",
        ok,
        f"audit_status={rejected.audit_status if rejected else None} tasks={tasks_after_reject} "
        f"二次reject拦截={reject_twice_blocked} reject后approve拦截={approve_after_reject_blocked}",
    )


async def check_approved_cannot_reject(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    card, _ = _create_pending_card(session, suffix=f"no-rj-{suffix}")
    svc = AdminReviewService(session)
    svc.approve_knowledge(
        card.id,
        KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER),
    )
    session.expire_all()
    try:
        svc.reject_knowledge(
            card.id,
            KnowledgeReviewActionRequest(
                action="reject",
                audit_user=AUDIT_USER,
                audit_remark="不应成功",
            ),
        )
        blocked = False
    except AdminReviewServiceError as exc:
        blocked = "待审核" in exc.message or "pending" in exc.message.lower()
    approved = session.get(KnowledgeCard, card.id)
    ok = blocked and approved is not None and approved.audit_status == "approved"
    return CheckResult(
        "4. approved 后禁止 reject",
        ok,
        f"reject拦截={blocked} audit_status={approved.audit_status if approved else None}",
    )


async def check_rag_after_approve(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    unique_q = f"{SUPPLEMENT_PREFIX}专用检索问题{suffix}如何验收？"
    card, _ = _create_pending_card(
        session,
        suffix=f"rag-{suffix}",
        title=f"{SUPPLEMENT_PREFIX}RAG检索卡片{suffix}",
        question=unique_q,
        with_contribution=False,
    )
    svc = AdminReviewService(session)
    svc.approve_knowledge(
        card.id,
        KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER),
    )
    await Stage3VectorSyncService(session).process_pending(limit=5)
    session.expire_all()
    synced = session.get(KnowledgeCard, card.id)
    runner = AskGraphV2Runner(session)
    state = await runner.run(question=unique_q, user_id=AUDIT_USER, source="stage5_supplement")
    level = state.get("confidence_level")
    score = float(state.get("top_score") or 0.0)
    ok = (
        synced is not None
        and synced.vector_status == "synced"
        and level in {"high", "medium"}
        and score > 0
    )
    return CheckResult(
        "5. 审核通过后 RAG 可检索",
        ok,
        f"vector_status={synced.vector_status if synced else None} "
        f"confidence={level} top_score={score:.4f} status={state.get('status')}",
    )


async def _find_or_create_duplicate_contribution(session, suffix: str) -> KnowledgeContribution | None:
    repo = AdminReviewRepository(session)
    rows = repo.list_contributions(offset=0, limit=5, status="duplicate_suspected")
    for row in rows:
        if row.knowledge_card_id is None:
            return row
    router = CommandRouter(session)
    gid = f"supp5-dup-{suffix}"
    uid = f"supp5-dup-u-{suffix}"
    await router.route(
        WeComMessage(
            message_id=str(uuid.uuid4()),
            group_id=gid,
            user_id=uid,
            user_name="supplement-check",
            content="【沉淀】",
        )
    )
    resp = await router.route(
        WeComMessage(
            message_id=str(uuid.uuid4()),
            group_id=gid,
            user_id=uid,
            user_name="supplement-check",
            content=DUPLICATE_CARD,
        )
    )
    session.commit()
    if resp.contribution_id:
        return repo.get_contribution_by_contribution_id(resp.contribution_id)
    return None


async def check_duplicate_mark_boundary(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    contrib = await _find_or_create_duplicate_contribution(session, suffix)
    if contrib is None:
        return CheckResult("6. duplicate_suspected 标记边界", False, "未找到或创建 duplicate_suspected 投稿")
    cards_before = session.scalar(select(func.count()).select_from(KnowledgeCard))
    tasks_before = session.scalar(select(func.count()).select_from(VectorSyncTask))
    svc = AdminReviewService(session)
    action = "ignore_duplicate" if contrib.status == "duplicate_suspected" else "mark_reviewed"
    svc.mark_contribution_reviewed(
        contrib.contribution_id,
        ContributionMarkReviewRequest(action=action, reviewer=AUDIT_USER, remark="补充验收"),
    )
    session.expire_all()
    refreshed = AdminReviewRepository(session).get_contribution_by_contribution_id(contrib.contribution_id)
    cards_after = session.scalar(select(func.count()).select_from(KnowledgeCard))
    tasks_after = session.scalar(select(func.count()).select_from(VectorSyncTask))
    ok = (
        refreshed is not None
        and refreshed.knowledge_card_id is None
        and cards_after == cards_before
        and tasks_after == tasks_before
        and refreshed.status in {"reviewed", "ignore_duplicate"}
    )
    return CheckResult(
        "6. duplicate_suspected 标记边界",
        ok,
        f"action={action} status={refreshed.status if refreshed else None} "
        f"knowledge_card_id={refreshed.knowledge_card_id if refreshed else None} "
        f"cardsΔ={cards_after - cards_before} tasksΔ={tasks_after - tasks_before}",
    )


async def _find_or_create_risk_contribution(session, suffix: str) -> KnowledgeContribution | None:
    repo = AdminReviewRepository(session)
    rows = repo.list_contributions(offset=0, limit=5, status="risk_blocked")
    if rows:
        return rows[0]
    router = CommandRouter(session)
    gid = f"supp5-risk-{suffix}"
    uid = f"supp5-risk-u-{suffix}"
    text = RISK_CARD.format(suffix=suffix)
    await router.route(
        WeComMessage(message_id=str(uuid.uuid4()), group_id=gid, user_id=uid, user_name="supp", content="【沉淀】")
    )
    resp = await router.route(
        WeComMessage(message_id=str(uuid.uuid4()), group_id=gid, user_id=uid, user_name="supp", content=text)
    )
    session.commit()
    if resp.contribution_id:
        return repo.get_contribution_by_contribution_id(resp.contribution_id)
    return None


async def check_risk_mark_boundary(session) -> CheckResult:
    suffix = uuid.uuid4().hex[:8]
    contrib = await _find_or_create_risk_contribution(session, suffix)
    if contrib is None or contrib.status != "risk_blocked":
        return CheckResult(
            "7. risk_blocked 标记边界",
            False,
            f"未获得 risk_blocked 投稿 status={contrib.status if contrib else None}",
        )
    cards_before = session.scalar(select(func.count()).select_from(KnowledgeCard))
    tasks_before = session.scalar(select(func.count()).select_from(VectorSyncTask))
    svc = AdminReviewService(session)
    svc.mark_contribution_reviewed(
        contrib.contribution_id,
        ContributionMarkReviewRequest(action="keep_blocked", reviewer=AUDIT_USER, remark="补充验收"),
    )
    session.expire_all()
    refreshed = AdminReviewRepository(session).get_contribution_by_contribution_id(contrib.contribution_id)
    cards_after = session.scalar(select(func.count()).select_from(KnowledgeCard))
    tasks_after = session.scalar(select(func.count()).select_from(VectorSyncTask))
    ok = (
        refreshed is not None
        and refreshed.knowledge_card_id is None
        and cards_after == cards_before
        and tasks_after == tasks_before
        and refreshed.status == "keep_blocked"
    )
    return CheckResult(
        "7. risk_blocked 标记边界",
        ok,
        f"status={refreshed.status if refreshed else None} knowledge_card_id={refreshed.knowledge_card_id if refreshed else None} "
        f"cardsΔ={cards_after - cards_before} tasksΔ={tasks_after - tasks_before}",
    )


def _response_has_sensitive_blob(blob: str) -> list[str]:
    hits: list[str] = []
    for pat in _SENSITIVE_PATTERNS:
        if pat.search(blob):
            hits.append(pat.pattern[:40])
    return hits


def check_api_desensitize(session) -> CheckResult:
    svc = AdminReviewService(session)
    listing = svc.list_contributions(page=1, page_size=5)
    list_blob = str(listing)
    list_hits = _response_has_sensitive_blob(list_blob)
    has_raw_in_list = any("raw_content" in str(item) for item in listing.get("items", []))
    has_preview = all("content_preview" in item for item in listing.get("items", [])) if listing.get("items") else True

    detail_hits: list[str] = []
    has_full_raw = False
    items = listing.get("items") or []
    if items:
        cid = items[0].get("contribution_id")
        if cid:
            detail = svc.get_contribution_detail(cid).model_dump()
            detail_blob = str(detail)
            detail_hits = _response_has_sensitive_blob(detail_blob)
            has_full_raw = "raw_content" in detail and bool(detail.get("raw_content"))

    ok = not list_hits and not detail_hits and not has_raw_in_list and has_preview and not has_full_raw
    return CheckResult(
        "8. 后台接口脱敏",
        ok,
        f"列表含raw_content={has_raw_in_list} 含preview={has_preview} "
        f"敏感命中 list={len(list_hits)} detail={len(detail_hits)} detail含raw_content键={has_full_raw}",
    )


def check_page_api_consistency(session) -> CheckResult:
    """页面路由与 API 均调用 AdminReviewService，状态变化一致。"""
    from app.routers import admin_page_router, admin_review_router

    page_src = inspect.getsource(admin_page_router)
    api_src = inspect.getsource(admin_review_router)
    static_ok = (
        "AdminReviewService" in page_src
        and "approve_knowledge" in page_src
        and "reject_knowledge" in page_src
        and "AdminReviewService" in api_src
        and "approve_knowledge" in api_src
        and "reject_knowledge" in api_src
    )

    suffix = uuid.uuid4().hex[:8]
    card_api, _ = _create_pending_card(session, suffix=f"api-{suffix}")
    card_page, _ = _create_pending_card(session, suffix=f"page-{suffix}")
    svc = AdminReviewService(session)
    api_result = svc.approve_knowledge(
        card_api.id,
        KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER, audit_remark="api-path"),
    )
    page_result = svc.approve_knowledge(
        card_page.id,
        KnowledgeReviewActionRequest(action="approve", audit_user=AUDIT_USER, audit_remark="page-path"),
    )
    session.expire_all()
    c_api = session.get(KnowledgeCard, card_api.id)
    c_page = session.get(KnowledgeCard, card_page.id)
    state_ok = (
        c_api is not None
        and c_page is not None
        and c_api.audit_status == c_page.audit_status == "approved"
        and c_api.enabled == c_page.enabled == 1
        and c_api.vector_status == c_page.vector_status == "pending"
        and api_result.get("vector_sync_task_created")
        and page_result.get("vector_sync_task_created")
    )
    ok = static_ok and state_ok
    return CheckResult(
        "9. 页面与 API 一致性",
        ok,
        f"静态调用AdminReviewService={static_ok} api/page状态一致={state_ok} "
        f"audit_status={c_api.audit_status if c_api else None}",
    )


async def run_all(env_file: str) -> int:
    apply_env_file(env_file)
    print("Stage5 补充验收开始")
    results: list[CheckResult] = []

    results.append(check_vector_status_unified())

    with SessionLocal() as session:
        results.append(await check_approve_idempotent(session))
        results.append(await check_reject_idempotent(session))
        results.append(await check_approved_cannot_reject(session))
        results.append(await check_rag_after_approve(session))
        results.append(await check_duplicate_mark_boundary(session))
        results.append(await check_risk_mark_boundary(session))
        results.append(check_api_desensitize(session))
        results.append(check_page_api_consistency(session))

    print("\n========== 补充验收结果 ==========")
    all_ok = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.detail}")
        if not r.passed:
            all_ok = False

    if all_ok:
        print("\n[PASS] Stage5 补充验收全部通过")
        return 0
    print("\n[FAIL] Stage5 补充验收存在失败项")
    return 1


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run_all(args.env_file))
    except Exception as exc:
        print(f"[FAIL] 补充验收异常：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
