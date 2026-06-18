#!/usr/bin/env python
"""Stage5 后台审核能力检查：字段约定、列表查询、关联与 Service 可调用性。"""

from __future__ import annotations

import argparse
import inspect
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.admin_review_repository import AdminReviewRepository
from app.schemas.admin_review_schema import KnowledgeReviewActionRequest
from app.services.admin_review_service import AdminReviewService
from app.services.knowledge_service import KnowledgeService

DEFAULT_ENV_FILE = "docs/prod/.env"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage5 后台审核检查")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def check_audit_status_field(session) -> CheckResult:
    columns = {c.name for c in KnowledgeCard.__table__.columns}
    ok = "audit_status" in columns and "status" not in columns
    pending_count = AdminReviewRepository(session).count_pending_knowledge()
    audit_src = inspect.getsource(KnowledgeService.audit)
    uses_pending = 'audit_status != "pending"' in audit_src
    ok = ok and uses_pending
    return CheckResult(
        "1. knowledge_card 使用 audit_status",
        ok,
        f"audit_status={'有' if 'audit_status' in columns else '无'}；"
        f"status列={'有(异常)' if 'status' in columns else '无'}；pending数={pending_count}",
    )


def check_pending_query(session) -> CheckResult:
    repo = AdminReviewRepository(session)
    items = repo.list_pending_knowledge(limit=5)
    ok = isinstance(items, list)
    sample = items[0].id if items else None
    return CheckResult(
        "2. pending 知识可查询",
        ok,
        f"查到 {len(items)} 条 pending；样例 id={sample}",
    )


def check_contribution_link(session) -> CheckResult:
    stmt = (
        select(KnowledgeContribution)
        .where(KnowledgeContribution.knowledge_card_id.isnot(None))
        .order_by(KnowledgeContribution.id.desc())
        .limit(1)
    )
    contrib = session.scalar(stmt)
    if contrib is None:
        return CheckResult("3. contribution 关联", True, "暂无带 knowledge_card_id 的投稿（跳过）")
    card = session.get(KnowledgeCard, contrib.knowledge_card_id)
    ok = card is not None
    return CheckResult(
        "3. contribution 关联",
        ok,
        f"contribution_id={contrib.contribution_id[:8]}… card_id={contrib.knowledge_card_id} "
        f"card.audit_status={card.audit_status if card else None}",
    )


def check_service_callable(session) -> CheckResult:
    svc = AdminReviewService(session)
    data = svc.list_contributions(page=1, page_size=5)
    pending = svc.list_pending_knowledge(page=1, page_size=5)
    ok = "items" in data and "items" in pending
    return CheckResult(
        "4. AdminReviewService 可调用",
        ok,
        f"contributions={data.get('total')} pending={pending.get('total')}",
    )


def check_special_contributions(session) -> CheckResult:
    dup = AdminReviewRepository(session).list_contributions(
        limit=3, duplicate_suspected=True, offset=0
    )
    risk = AdminReviewRepository(session).list_contributions(
        limit=3, status="risk_blocked", offset=0
    )
    ok = True
    return CheckResult(
        "5. duplicate/risk 投稿可查询",
        ok,
        f"duplicate_suspected样例={len(dup)} risk_blocked样例={len(risk)}",
    )


def check_reject_validation(session) -> CheckResult:
    """拒绝空原因应失败（不创建测试卡片）。"""
    pending = AdminReviewRepository(session).list_pending_knowledge(limit=1)
    if not pending:
        return CheckResult("6. reject 校验", True, "无 pending 卡片，跳过空原因校验")
    card_id = pending[0].id
    svc = AdminReviewService(session)
    try:
        svc.reject_knowledge(
            card_id,
            KnowledgeReviewActionRequest(action="reject", audit_user="stage5-check", audit_remark=""),
        )
        return CheckResult("6. reject 校验", False, "空原因拒绝未拦截")
    except Exception as exc:
        ok = "拒绝" in str(getattr(exc, "message", exc))
        return CheckResult("6. reject 校验", ok, f"空原因拒绝被拦截：{getattr(exc, 'message', exc)}")


def run_all(env_file: str) -> int:
    apply_env_file(env_file)
    suffix = uuid.uuid4().hex[:6]
    print(f"Stage5 后台审核检查开始 suffix={suffix}")
    results: list[CheckResult] = []

    with SessionLocal() as session:
        results.append(check_audit_status_field(session))
        results.append(check_pending_query(session))
        results.append(check_contribution_link(session))
        results.append(check_service_callable(session))
        results.append(check_special_contributions(session))
        results.append(check_reject_validation(session))

    print("\n========== 检查结果 ==========")
    all_ok = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.detail}")
        if not r.passed:
            all_ok = False

    if all_ok:
        print("\n[PASS] Stage5 后台审核检查全部通过")
        return 0
    print("\n[FAIL] Stage5 后台审核检查存在失败项")
    return 1


def main() -> int:
    args = parse_args()
    try:
        return run_all(args.env_file)
    except Exception as exc:
        print(f"[FAIL] 检查异常：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
