#!/usr/bin/env python
"""Stage5 审核流验收：approve 入队向量同步 + reject 不入队 + contribution 状态联动。"""

from __future__ import annotations

import argparse
import asyncio
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
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.models.vector_sync_task import VectorSyncTask
from app.repositories.stage3_repository import VectorSyncTaskRepository
from app.schemas.admin_review_schema import KnowledgeReviewActionRequest
from app.services.admin_review_service import AdminReviewService, AdminReviewServiceError
from app.services.knowledge_content import card_to_content_dict, compute_content_hash
from app.services.stage3_vector_sync_service import Stage3VectorSyncService

DEFAULT_ENV_FILE = "docs/prod/.env"
TITLE_PREFIX = "【阶段5验收】"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage5 审核流验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--skip-worker", action="store_true", help="跳过 vector worker 执行")
    return parser.parse_args()


def _create_pending_with_contribution(session, suffix: str) -> tuple[KnowledgeCard, KnowledgeContribution]:
    """创建 pending 知识及关联投稿（stage5_check 来源）。"""
    title = f"{TITLE_PREFIX}审核流测试{suffix}"
    card = KnowledgeCard(
        title=title,
        question=f"{TITLE_PREFIX}阶段5审核通过/拒绝流程如何验证？",
        answer=f"{TITLE_PREFIX}通过 AdminReviewService 审核并检查 vector_sync_task。",
        system_name="数字员工助手",
        module_name="知识审核",
        tags="stage5,验收,审核",
        scene="阶段5验收",
        solution=f"{TITLE_PREFIX}运行 check_stage5_review_flow.py 验证审核闭环。",
        source_group="stage5_check",
        source_user="stage5-script",
        audit_status="pending",
        enabled=0,
        deleted=0,
        vector_status="waiting_review",
        version=1,
        create_user="stage5-check",
        update_user="stage5-check",
    )
    card.content_hash = compute_content_hash(card_to_content_dict(card))
    session.add(card)
    session.flush()

    contrib = KnowledgeContribution(
        contribution_id=str(uuid.uuid4()),
        source="stage5_check",
        user_id="stage5-check",
        user_name="stage5-script",
        raw_content=sanitize_text(f"{title} 验收数据", max_length=200),
        status="pending_card_created",
        knowledge_card_id=card.id,
        duplicate_suspected=False,
        risk_level="none",
    )
    session.add(contrib)
    session.commit()
    session.refresh(card)
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


async def run_checks(env_file: str, *, skip_worker: bool) -> int:
    apply_env_file(env_file)
    suffix = uuid.uuid4().hex[:8]
    results: list[CheckResult] = []
    print(f"Stage5 审核流验收开始 suffix={suffix}")

    with SessionLocal() as session:
        approve_card, approve_contrib = _create_pending_with_contribution(session, f"ap-{suffix}")
        svc = AdminReviewService(session)

        approve_result = svc.approve_knowledge(
            approve_card.id,
            KnowledgeReviewActionRequest(
                action="approve",
                audit_user="stage5-check",
                audit_remark="阶段5验收自动通过",
            ),
        )
        session.expire_all()
        approved = session.get(KnowledgeCard, approve_card.id)
        contrib_after = session.scalar(
            select(KnowledgeContribution).where(
                KnowledgeContribution.contribution_id == approve_contrib.contribution_id
            )
        )
        task_count = _count_tasks(session, approve_card.id)

        approve_ok = (
            approved is not None
            and approved.audit_status == "approved"
            and approved.enabled == 1
            and approved.vector_status == "pending"
            and approve_result.get("vector_sync_task_created") is True
            and task_count >= 1
            and contrib_after is not None
            and contrib_after.status == "approved"
        )
        results.append(
            CheckResult(
                "1. 审核通过",
                approve_ok,
                f"audit_status={approved.audit_status if approved else None} enabled={approved.enabled if approved else None} "
                f"vector_status={approved.vector_status if approved else None} tasks={task_count} "
                f"contrib.status={contrib_after.status if contrib_after else None}",
            )
        )

        if not skip_worker and approve_ok:
            worker_stats = await Stage3VectorSyncService(session).process_pending(limit=10)
            session.expire_all()
            synced = session.get(KnowledgeCard, approve_card.id)
            worker_ok = synced is not None and synced.vector_status == "synced"
            results.append(
                CheckResult(
                    "2. worker 同步 Qdrant",
                    worker_ok,
                    f"worker={worker_stats} vector_status={synced.vector_status if synced else None}",
                )
            )
        else:
            results.append(CheckResult("2. worker 同步 Qdrant", True, "已跳过 worker 执行"))

        reject_card, reject_contrib = _create_pending_with_contribution(session, f"rj-{suffix}")
        tasks_before = _count_tasks(session, reject_card.id)
        try:
            svc.reject_knowledge(
                reject_card.id,
                KnowledgeReviewActionRequest(
                    action="reject",
                    audit_user="stage5-check",
                    audit_remark="阶段5验收自动拒绝",
                ),
            )
        except AdminReviewServiceError as exc:
            results.append(CheckResult("3. 审核拒绝", False, exc.message))
        else:
            session.expire_all()
            rejected = session.get(KnowledgeCard, reject_card.id)
            reject_contrib_db = session.scalar(
                select(KnowledgeContribution).where(
                    KnowledgeContribution.contribution_id == reject_contrib.contribution_id
                )
            )
            tasks_after = _count_tasks(session, reject_card.id)
            reject_ok = (
                rejected is not None
                and rejected.audit_status == "rejected"
                and rejected.enabled == 0
                and rejected.audit_remark
                and reject_contrib_db is not None
                and reject_contrib_db.status == "rejected"
                and tasks_after == tasks_before == 0
            )
            results.append(
                CheckResult(
                    "3. 审核拒绝",
                    reject_ok,
                    f"audit_status={rejected.audit_status if rejected else None} enabled={rejected.enabled if rejected else None} "
                    f"remark={'有' if rejected and rejected.audit_remark else '无'} tasks={tasks_after} "
                    f"contrib.status={reject_contrib_db.status if reject_contrib_db else None}",
                )
            )

        repeat_card, _ = _create_pending_with_contribution(session, f"dup-{suffix}")
        svc.approve_knowledge(
            repeat_card.id,
            KnowledgeReviewActionRequest(action="approve", audit_user="stage5-check"),
        )
        session.expire_all()
        try:
            svc.approve_knowledge(
                repeat_card.id,
                KnowledgeReviewActionRequest(action="approve", audit_user="stage5-check"),
            )
            repeat_ok = False
        except AdminReviewServiceError as exc:
            repeat_ok = "待审核" in exc.message or "pending" in exc.message.lower()
        results.append(
            CheckResult(
                "4. 非 pending 重复审核拦截",
                repeat_ok,
                "已 approved 卡片再次 approve 被拒绝" if repeat_ok else "重复审核未拦截",
            )
        )

    print("\n========== 验收结果 ==========")
    all_ok = True
    for r in results:
        mark = "PASS" if r.passed else "FAIL"
        print(f"[{mark}] {r.name}")
        print(f"       {r.detail}")
        if not r.passed:
            all_ok = False

    if all_ok:
        print("\n[PASS] Stage5 审核流验收全部通过")
        return 0
    print("\n[FAIL] Stage5 审核流验收存在失败项")
    return 1


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(run_checks(args.env_file, skip_worker=args.skip_worker))
    except Exception as exc:
        print(f"[FAIL] 验收异常：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
