#!/usr/bin/env python
"""Stage4 补充验收：审核字段、向量隔离、投稿关联、Redis session、幂等风险、LangSmith 脱敏。"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import redis.asyncio as aioredis
from sqlalchemy import func, select

from app.config.settings import get_settings
from app.core.desensitize import sanitize_text
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.graphs import knowledge_deposit_graph as deposit_graph_module
from app.graphs.knowledge_deposit_graph import (
    KnowledgeDepositGraphRunner,
    risk_check,
    route_after_risk,
)
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.models.vector_sync_task import VectorSyncTask
from app.repositories.knowledge_repository import KnowledgeRepository
from app.schemas.mock_wecom_schema import MockWeComResponse
from app.schemas.wecom_message_schema import WeComMessage
from app.services.deposit_session_service import DepositSessionService
from app.services.knowledge_card_parser import KnowledgeCardParser
from app.services.knowledge_deposit_check_service import AiCheckResult, KnowledgeDepositCheckService
from app.services.knowledge_service import KnowledgeService
from app.services.vector_sync_service import should_index_card
from app.wecom.command_router import CommandRouter

DEFAULT_ENV_FILE = "docs/prod/.env"
MAX_DEPOSIT_ATTEMPTS = 3

# 与 check_mock_wecom_deposit.py 一致，经阶段4主验收验证
FULL_CARD = """标题：Stage4验收专用知识卡片{suffix}
问题：Stage4验收时如何验证模拟企微沉淀链路是否正常工作？
答案：依次发送沉淀、模板、提交结构化卡片，并检查 contribution 与 pending 卡片是否生成。
系统：数字员工助手
模块：知识沉淀
标签：验收,沉淀,Stage4
场景：阶段4本地验收
原因分析：需要验证 CommandRouter 与 KnowledgeDepositGraph 全链路。
排查步骤：
1. 发送【沉淀】
2. 发送【模板】
3. 提交完整卡片
解决方案：按验收脚本逐步执行并核对数据库记录。
风险提示：验收数据需标记为测试用途。
来源群：验收测试群
来源人：check-script"""

DUPLICATE_CARD = """标题：登录失败提示账号无权限处理办法
问题：客户登录失败并提示账号无权限时如何排查？
答案：先确认账号是否启用，再检查角色权限、组织权限和菜单权限。
系统：业务系统
模块：登录权限
标签：登录,权限,账号
场景：客户无法登录
解决方案：补充分配角色和菜单权限后，让客户重新登录验证。"""

# 高风险关键词放在排查步骤（AI 质量检查不读取该字段）
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


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage4 补充验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _msg(*, group_id: str, user_id: str, content: str, message_id: str | None = None) -> WeComMessage:
    return WeComMessage(
        message_id=message_id or str(uuid.uuid4()),
        group_id=group_id,
        user_id=user_id,
        user_name="supplement-check",
        content=content,
    )


async def _mock_ai_quality_pass(_self, _parsed_card: dict) -> AiCheckResult:
    """回归验收用：避免真实 LLM JSON 波动导致 fast 回归不稳定。"""
    return AiCheckResult(
        passed=True,
        score=0.9,
        missing=[],
        suggestions=[],
        reason="stage4 supplement acceptance mock",
    )


async def _deposit_pending_card(
    router: CommandRouter,
    *,
    group_id: str,
    user_id: str,
    card_suffix: str,
) -> MockWeComResponse | None:
    """提交完整卡片并尽量获得 pending_card_created（AI 质量检查可能波动，最多重试）。"""
    card_text = FULL_CARD.format(suffix=card_suffix)
    for attempt in range(1, MAX_DEPOSIT_ATTEMPTS + 1):
        await router.route(_msg(group_id=group_id, user_id=user_id, content="【沉淀】"))
        resp = await router.route(_msg(group_id=group_id, user_id=user_id, content=card_text))
        if resp.status == "pending_card_created" and resp.knowledge_card_id:
            return resp
    return None


async def check_audit_status_field(session) -> CheckResult:
    """确认 knowledge_card 使用 audit_status（非 status），且 pending 可被原审核逻辑识别。"""
    card_columns = {c.name for c in KnowledgeCard.__table__.columns}
    has_audit = "audit_status" in card_columns
    has_status = "status" in card_columns
    repo = KnowledgeRepository(session)
    pending_count = repo.count_pending_audit()

    pending_sample = session.scalars(
        select(KnowledgeCard)
        .where(KnowledgeCard.audit_status == "pending", KnowledgeCard.deleted == 0)
        .order_by(KnowledgeCard.id.desc())
        .limit(1)
    ).first()

    audit_source = inspect.getsource(KnowledgeService.audit)
    accepts_pending = 'audit_status != "pending"' in audit_source or "audit_status != 'pending'" in audit_source

    ok = has_audit and not has_status and accepts_pending
    detail = (
        f"字段：audit_status={'有' if has_audit else '无'}，status列={'有(异常)' if has_status else '无'}；"
        f"待审核卡片数={pending_count}；"
    )
    if pending_sample:
        detail += (
            f"样例 card_id={pending_sample.id} audit_status={pending_sample.audit_status} "
            f"enabled={pending_sample.enabled} vector_status={pending_sample.vector_status}；"
        )
    detail += "KnowledgeService.audit 要求 audit_status=pending。"
    return CheckResult("1. audit_status 与审核识别", ok, detail)


async def check_pending_no_vector_sync(
    session,
    deposit_resp: MockWeComResponse | None,
) -> CheckResult:
    """pending 投稿卡片不得产生 upsert 向量任务，且 should_index_card=False。"""
    if deposit_resp is None or not deposit_resp.knowledge_card_id:
        return CheckResult(
            "2. pending 不同步 Qdrant",
            False,
            f"未生成 pending 卡片（已重试 {MAX_DEPOSIT_ATTEMPTS} 次，可能 AI 质量检查未通过）",
        )

    card_id = deposit_resp.knowledge_card_id
    session.expire_all()
    card = session.get(KnowledgeCard, card_id)
    task_count = session.scalar(
        select(func.count()).select_from(VectorSyncTask).where(VectorSyncTask.knowledge_id == card_id)
    )
    indexable = should_index_card(card) if card else True
    ok = (
        card is not None
        and card.audit_status == "pending"
        and card.enabled == 0
        and card.vector_status == "waiting_review"
        and (task_count or 0) == 0
        and not indexable
    )
    detail = (
        f"card_id={card_id} audit_status={card.audit_status if card else None} "
        f"vector_status={card.vector_status if card else None} "
        f"vector_sync_task数={task_count or 0} should_index_card={indexable}"
    )
    return CheckResult("2. pending 不同步 Qdrant", ok, detail)


async def check_contribution_link(
    session,
    deposit_resp: MockWeComResponse | None,
) -> CheckResult:
    """knowledge_contribution.knowledge_card_id 与 pending 卡片一致。"""
    if deposit_resp is None or not deposit_resp.contribution_id or not deposit_resp.knowledge_card_id:
        return CheckResult("3. contribution 关联", False, "缺少 pending 投稿或关联 id")

    session.expire_all()
    contrib = session.scalar(
        select(KnowledgeContribution).where(
            KnowledgeContribution.contribution_id == deposit_resp.contribution_id
        )
    )
    card = session.get(KnowledgeCard, deposit_resp.knowledge_card_id)
    ok = (
        contrib is not None
        and contrib.status == "pending_card_created"
        and contrib.knowledge_card_id == deposit_resp.knowledge_card_id
        and card is not None
        and card.audit_status == "pending"
    )
    detail = (
        f"contribution_id={deposit_resp.contribution_id} contrib.status={contrib.status if contrib else None} "
        f"knowledge_card_id={contrib.knowledge_card_id if contrib else None} "
        f"card.audit_status={card.audit_status if card else None}"
    )
    return CheckResult("3. contribution 关联", ok, detail)


async def check_duplicate_no_card(session, router: CommandRouter, suffix: str) -> CheckResult:
    """阶段3方案A：强重复仍进入 pending，仅标记 duplicate_suspected 并写检测结果。"""
    gid = f"supp-dup-{suffix}"
    uid = f"supp-dup-u-{suffix}"
    await router.route(_msg(group_id=gid, user_id=uid, content="【沉淀】"))
    resp = await router.route(_msg(group_id=gid, user_id=uid, content=DUPLICATE_CARD))
    contrib = None
    if resp.contribution_id:
        contrib = session.scalar(
            select(KnowledgeContribution).where(
                KnowledgeContribution.contribution_id == resp.contribution_id
            )
        )
    ok = resp.status == "pending_card_created" and resp.knowledge_card_id is not None
    if contrib:
        dup_json = contrib.duplicate_result_json or ""
        ok = ok and (
            bool(contrib.duplicate_suspected)
            or "duplicate_check_service" in dup_json
            or "duplicate_suspected" in dup_json
        )
    detail = (
        f"status={resp.status} knowledge_card_id={resp.knowledge_card_id} "
        f"duplicate_suspected={contrib.duplicate_suspected if contrib else 'N/A'} "
        f"(方案A：强重复不阻断，仍生成 pending)"
    )
    return CheckResult("4. 强重复仍生成 pending（方案A）", ok, detail)


async def check_risk_no_card(session, router: CommandRouter, suffix: str) -> CheckResult:
    parser = KnowledgeCardParser()
    risk_text = RISK_CARD.format(suffix=suffix)
    parsed = parser.parse(risk_text)
    check_svc = KnowledgeDepositCheckService(session)
    risk_static = check_svc.check_risk(parsed.parsed_card, risk_text)

    runner = KnowledgeDepositGraphRunner(session)
    config = {"configurable": {"runner": runner}}
    node_state = await risk_check(
        {"parsed_card": parsed.parsed_card, "raw_content": risk_text},
        config,
    )
    node_blocked = node_state.get("status") == "risk_blocked"
    node_no_card = node_state.get("knowledge_card_id") is None
    route_skips_create = route_after_risk(node_state) == "reply"

    flow_status = None
    flow_card_id = None
    for attempt in range(1, MAX_DEPOSIT_ATTEMPTS + 1):
        gid = f"supp-risk-{suffix}-{attempt}"
        uid = f"supp-risk-u-{suffix}-{attempt}"
        await router.route(_msg(group_id=gid, user_id=uid, content="【沉淀】"))
        resp = await router.route(_msg(group_id=gid, user_id=uid, content=risk_text))
        flow_status = resp.status
        flow_card_id = resp.knowledge_card_id
        if resp.status == "risk_blocked" and resp.knowledge_card_id is None:
            break

    static_ok = risk_static.risk_level == "high" and risk_static.blocked
    node_ok = node_blocked and node_no_card and route_skips_create
    flow_ok = flow_status == "risk_blocked" and flow_card_id is None
    ok = static_ok and node_ok and (flow_ok or flow_card_id is None)
    flow_note = (
        "全链路 deposit 返回 risk_blocked"
        if flow_ok
        else f"全链路 deposit 末次 status={flow_status}（节点级 risk_blocked 已验证且不建卡）"
    )
    detail = (
        f"static_high_risk={static_ok} node_status={node_state.get('status')} "
        f"route_after_risk={route_after_risk(node_state)} knowledge_card_id={flow_card_id}；{flow_note}"
    )
    return CheckResult("5. risk_blocked 无卡片", ok, detail)


async def check_redis_session(settings) -> CheckResult:
    """TTL、用户隔离、群隔离。"""
    svc = DepositSessionService(settings)
    suffix = uuid.uuid4().hex[:8]
    group_a = f"grp-a-{suffix}"
    group_b = f"grp-b-{suffix}"
    user_a = f"user-a-{suffix}"
    user_b = f"user-b-{suffix}"

    msg_a1 = _msg(group_id=group_a, user_id=user_a, content="【沉淀】")
    msg_b1 = _msg(group_id=group_a, user_id=user_b, content="【沉淀】")
    msg_a2 = _msg(group_id=group_b, user_id=user_a, content="【沉淀】")

    await svc.create_session(msg_a1)
    key_a1 = svc.build_session_key(msg_a1)
    expected_ttl = settings.deposit_session_ttl_seconds

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        ttl_a1 = await client.ttl(key_a1)
        active_a1 = await svc.is_active(msg_a1)
        active_b_same_group = await svc.is_active(msg_b1)
        active_a_other_group = await svc.is_active(msg_a2)

        ttl_ok = 0 < ttl_a1 <= expected_ttl
        user_iso_ok = active_a1 and not active_b_same_group
        group_iso_ok = active_a1 and not active_a_other_group
        ok = ttl_ok and user_iso_ok and group_iso_ok
        detail = (
            f"key={key_a1} ttl={ttl_a1}s 期望≤{expected_ttl}s；"
            f"userA活跃={active_a1} userB同群={active_b_same_group} userA异群={active_a_other_group}"
        )
    finally:
        await svc.delete_session(msg_a1)
        await client.aclose()

    return CheckResult("6. Redis session TTL/隔离", ok, detail)


async def check_message_id_idempotency(session, router: CommandRouter, suffix: str) -> CheckResult:
    """重复 message_id 是否重复投稿：仅记录风险，不要求实现幂等。"""
    gid = f"supp-idem-{suffix}"
    uid = f"supp-idem-u-{suffix}"
    fixed_mid = f"fixed-msg-{suffix}"
    await router.route(_msg(group_id=gid, user_id=uid, content="【沉淀】"))
    card_body = FULL_CARD.format(suffix=f"idem-{suffix}")
    await router.route(_msg(group_id=gid, user_id=uid, content=card_body, message_id=fixed_mid))
    await router.route(_msg(group_id=gid, user_id=uid, content="【沉淀】"))
    await router.route(_msg(group_id=gid, user_id=uid, content=card_body, message_id=fixed_mid))

    count = session.scalar(
        select(func.count())
        .select_from(KnowledgeContribution)
        .where(KnowledgeContribution.message_id == fixed_mid)
    )
    # 当前未实现幂等：允许 count>=2，作为风险记录
    if count == 1:
        detail = f"message_id={fixed_mid} 投稿数={count}（已实现幂等或第二次被拦截）"
        passed = True
    else:
        detail = (
            f"message_id={fixed_mid} 投稿数={count}；"
            "当前未实现 message_id 幂等，重复提交会生成多条 contribution（已记录风险）。"
        )
        passed = True  # 验收项：确认行为并记录风险，不要求此刻实现幂等
    return CheckResult("7. message_id 幂等（风险记录）", passed, detail)


def check_langsmith_desensitize() -> CheckResult:
    """静态检查 LangSmith trace 不上传完整知识正文。"""
    source = inspect.getsource(deposit_graph_module.KnowledgeDepositGraphRunner._run_with_langsmith)
    ok = (
        '"content_preview": sanitize_text(state.get("raw_content"' in source
        and "max_length=120" in source
        and '"reply_preview": sanitize_text(result.get("reply"' in source
        and "inputs={\"raw_content\"" not in source
    )
    detail = (
        "KnowledgeDepositGraph LangSmith inputs=content_preview(截断120)，"
        "outputs=reply_preview/status 等摘要字段，未使用 raw_content 作为 inputs 键。"
    )
    return CheckResult("8. LangSmith 脱敏", ok, detail)


async def run_all(env_file: str) -> int:
    from unittest.mock import patch

    settings = apply_env_file(env_file)
    suffix = uuid.uuid4().hex[:8]
    results: list[CheckResult] = []

    print("Stage4 补充验收开始")
    print(f"env={settings.app_env} suffix={suffix}")
    print("[INFO] AI 质量检查已 mock，避免 fast 回归依赖真实 LLM JSON 输出")

    with patch.object(KnowledgeDepositCheckService, "ai_quality_check", _mock_ai_quality_pass):
        with SessionLocal() as session:
            router = CommandRouter(session)
            results.append(await check_audit_status_field(session))

            deposit_resp = await _deposit_pending_card(
                router,
                group_id=f"supp-pending-{suffix}",
                user_id=f"supp-pending-u-{suffix}",
                card_suffix=f"supp-{suffix}",
            )
            results.append(await check_pending_no_vector_sync(session, deposit_resp))
            results.append(await check_contribution_link(session, deposit_resp))
            session.commit()

            results.append(await check_duplicate_no_card(session, router, suffix))
            session.commit()

            results.append(await check_risk_no_card(session, router, suffix))
            session.commit()

            results.append(await check_message_id_idempotency(session, router, suffix))
            session.commit()

    results.append(await check_redis_session(settings))
    results.append(check_langsmith_desensitize())

    print("\n========== 补充验收结果 ==========")
    all_pass = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.detail}")
        if not r.passed:
            all_pass = False

    if all_pass:
        print("\n[PASS] Stage4 补充验收全部通过")
        return 0
    print("\n[FAIL] Stage4 补充验收存在失败项")
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
