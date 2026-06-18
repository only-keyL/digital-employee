#!/usr/bin/env python
"""生产 V1 增强阶段 5：运营看板验收脚本。"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, select

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.feedback_log import FeedbackLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.models.question_log import QuestionLog
from app.models.unanswered_question import UnansweredQuestion
from app.repositories.operation_dashboard_repository import OperationDashboardRepository
from app.services.operation_dashboard_service import OperationDashboardService

DEFAULT_ENV_FILE = "docs/prod/.env"
MARKER = "__stage5_dashboard__"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段5 运营看板验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def check_imports() -> list[str]:
    failures: list[str] = []
    try:
        from app.schemas.operation_dashboard_schema import OperationDashboardSummary

        _ = OperationDashboardSummary
        print("[PASS] 运营看板 Schema 导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 运营看板 Schema 导入失败：{exc}")

    try:
        from app.routers.operation_dashboard_router import (
            get_operation_dashboard_summary,
            get_operation_dashboard_tops,
        )

        _ = get_operation_dashboard_summary, get_operation_dashboard_tops
        print("[PASS] 运营看板 Router 导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 运营看板 Router 导入失败：{exc}")

    try:
        _ = OperationDashboardService(SessionLocal())
        print("[PASS] OperationDashboardService 导入通过")
        _ = OperationDashboardRepository(SessionLocal())
        print("[PASS] OperationDashboardRepository 导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] Service/Repository 导入失败：{exc}")
    return failures


def _cleanup(session, ids: dict) -> None:
    for log_id in ids.get("question_log_ids", []):
        session.execute(delete(FeedbackLog).where(FeedbackLog.question_log_id == log_id))
    for fb_id in ids.get("feedback_ids", []):
        session.execute(delete(FeedbackLog).where(FeedbackLog.id == fb_id))
    for dup_id in ids.get("duplicate_ids", []):
        session.execute(delete(KnowledgeDuplicateCheckLog).where(KnowledgeDuplicateCheckLog.id == dup_id))
    for u_id in ids.get("unanswered_ids", []):
        session.execute(delete(UnansweredQuestion).where(UnansweredQuestion.id == u_id))
    for log_id in ids.get("question_log_ids", []):
        session.execute(delete(QuestionLog).where(QuestionLog.id == log_id))
    for card_id in ids.get("card_ids", []):
        session.execute(delete(KnowledgeCard).where(KnowledgeCard.id == card_id))
    session.commit()


def run_data_checks() -> list[str]:
    failures: list[str] = []
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    batch_start = datetime.now()
    now = batch_start
    ids: dict = {
        "question_log_ids": [],
        "feedback_ids": [],
        "card_ids": [],
        "duplicate_ids": [],
        "unanswered_ids": [],
    }

    try:
        card = KnowledgeCard(
            title=f"{MARKER} 风险卡片 {suffix}",
            question="风险测试",
            answer="答案",
            audit_status="approved",
            enabled=1,
            deleted=0,
            useful_count=1,
            useless_count=5,
            supplement_count=2,
            need_review=1,
            quality_score=0.2,
            vector_status="success",
        )
        session.add(card)
        session.flush()
        ids["card_ids"].append(card.id)

        logs = [
            QuestionLog(
                request_id=f"{MARKER}-1-{suffix}",
                question_raw=f"{MARKER} q1",
                question_masked=f"{MARKER} q1",
                rewritten_question=f"{MARKER} q1",
                user_id=MARKER,
                source_type=MARKER,
                intent="question",
                matched=1,
                confidence_level="high",
                answer_status="hit",
                system_name="合同系统",
                module_name="审批流",
                primary_matched_card_id=card.id,
                primary_matched_card_title=card.title,
                latency_ms=1000,
                create_time=now,
            ),
            QuestionLog(
                request_id=f"{MARKER}-2-{suffix}",
                question_raw=f"{MARKER} q2",
                question_masked=f"{MARKER} q2",
                rewritten_question=f"{MARKER} q2",
                user_id=MARKER,
                source_type=MARKER,
                intent="question",
                matched=1,
                confidence_level="medium",
                answer_status="medium_confidence",
                system_name="合同系统",
                module_name="审批流",
                primary_matched_card_id=card.id,
                primary_matched_card_title=card.title,
                latency_ms=2000,
                create_time=now,
            ),
            QuestionLog(
                request_id=f"{MARKER}-3-{suffix}",
                question_raw=f"{MARKER} q3",
                question_masked=f"{MARKER} q3",
                rewritten_question=f"{MARKER} q3",
                user_id=MARKER,
                source_type=MARKER,
                intent="question",
                matched=0,
                confidence_level="low",
                answer_status="low_confidence",
                latency_ms=3000,
                create_time=now,
            ),
            QuestionLog(
                request_id=f"{MARKER}-4-{suffix}",
                question_raw=f"{MARKER} q4",
                question_masked=f"{MARKER} q4",
                rewritten_question=f"{MARKER} q4",
                user_id=MARKER,
                source_type=MARKER,
                intent="question",
                matched=0,
                confidence_level="none",
                answer_status="miss",
                latency_ms=4000,
                create_time=now,
            ),
        ]
        session.add_all(logs)
        session.flush()
        ids["question_log_ids"] = [log.id for log in logs]

        feedback_rows = [
            FeedbackLog(
                question_log_id=logs[0].id,
                user_id=MARKER,
                feedback_type="useful",
                status="new",
                create_time=now,
            ),
            FeedbackLog(
                question_log_id=logs[1].id,
                user_id=MARKER,
                feedback_type="useful",
                status="new",
                create_time=now,
            ),
            FeedbackLog(
                question_log_id=logs[2].id,
                user_id=MARKER,
                feedback_type="useless",
                status="new",
                create_time=now,
            ),
            FeedbackLog(
                question_log_id=logs[3].id,
                user_id=MARKER,
                feedback_type="supplement",
                supplement_text="补充内容",
                status="new",
                create_time=now,
            ),
        ]
        session.add_all(feedback_rows)
        session.flush()
        ids["feedback_ids"] = [row.id for row in feedback_rows]

        dup_rows = [
            KnowledgeDuplicateCheckLog(
                source_card_id=card.id,
                source_type=MARKER,
                check_level="high_duplicate",
                check_result="duplicate_warning",
                created_at=now,
            ),
            KnowledgeDuplicateCheckLog(
                source_card_id=card.id,
                source_type=MARKER,
                check_level="suspected_duplicate",
                check_result="duplicate_warning",
                created_at=now,
            ),
            KnowledgeDuplicateCheckLog(
                source_card_id=card.id,
                source_type=MARKER,
                check_level="none",
                check_result="no_duplicate",
                created_at=now,
            ),
        ]
        session.add_all(dup_rows)
        session.flush()
        ids["duplicate_ids"] = [row.id for row in dup_rows]

        unanswered = UnansweredQuestion(
            question_log_id=logs[3].id,
            question=f"{MARKER} 未命中",
            normalized_question=f"{MARKER}-unanswered-{suffix}",
            summary=f"{MARKER} 未命中",
            frequency=9,
            status="pending",
            last_seen_time=datetime.now(),
        )
        session.add(unanswered)
        session.flush()
        ids["unanswered_ids"].append(unanswered.id)
        session.commit()
        print("[PASS] 测试数据准备通过")

        repo = OperationDashboardRepository(session)
        batch_total = repo.count_questions(start_time=batch_start)
        batch_matched = repo.count_matched_questions(start_time=batch_start)
        if batch_total < 4:
            failures.append(f"批次提问数不足：{batch_total}")
            print("[FAIL] 问答运行指标统计未通过")
        elif batch_matched < 2:
            failures.append(f"批次命中数不足：{batch_matched}")
            print("[FAIL] 问答运行指标统计未通过")
        else:
            hit_rate = batch_matched / batch_total if batch_total else 0
            if abs(hit_rate - 0.5) > 0.01 and batch_matched == 2 and batch_total == 4:
                pass
            print("[PASS] 问答运行指标统计通过")

        conf = repo.get_confidence_distribution(start_time=batch_start)
        if conf.get("high", 0) < 1 or conf.get("low", 0) < 1:
            failures.append("置信度分布不符合预期")
            print("[FAIL] 置信度分布统计未通过")
        else:
            print("[PASS] 置信度分布统计通过")

        fb = repo.get_feedback_distribution(start_time=batch_start)
        if fb.get("useful", 0) < 2 or fb.get("useless", 0) < 1 or fb.get("supplement", 0) < 1:
            failures.append("反馈分布不符合预期")
            print("[FAIL] 反馈指标统计未通过")
        else:
            effective = fb["useful"] / (fb["useful"] + fb["useless"])
            if effective <= 0:
                failures.append("回答有效率计算错误")
                print("[FAIL] 反馈指标统计未通过")
            else:
                print("[PASS] 反馈指标统计通过")

        know = repo.get_knowledge_status_distribution()
        if know.get("total", 0) < 1:
            failures.append("知识库指标为空")
            print("[FAIL] 知识库指标统计未通过")
        else:
            print("[PASS] 知识库指标统计通过")

        dup = repo.get_duplicate_distribution(start_time=batch_start)
        if dup.get("high_duplicate", 0) < 1 or dup.get("suspected_duplicate", 0) < 1:
            failures.append("重复检测分布不符合预期")
            print("[FAIL] 重复检测指标统计未通过")
        else:
            print("[PASS] 重复检测指标统计通过")

        svc = OperationDashboardService(session)
        summary = svc.get_summary(days=7)
        if summary.question.total_count < batch_total:
            failures.append("summary 总提问数异常")
            print("[FAIL] summary 聚合异常")
        else:
            print("[PASS] summary 聚合通过")

        tops = svc.get_top_lists(days=7, limit=10)
        if not tops.top_unanswered:
            failures.append("top_unanswered 为空")
            print("[FAIL] Top 列表统计未通过")
        elif not tops.top_modules:
            failures.append("top_modules 为空")
            print("[FAIL] Top 列表统计未通过")
        elif not tops.top_referenced_cards:
            failures.append("top_referenced_cards 为空")
            print("[FAIL] Top 列表统计未通过")
        elif not tops.risk_cards:
            failures.append("risk_cards 为空")
            print("[FAIL] Top 列表统计未通过")
        else:
            print("[PASS] Top 列表统计通过")

        vm = svc.get_dashboard_view_model(days=7)
        required = {"summary", "tops", "intro", "days"}
        if not required.issubset(vm.keys()):
            failures.append("视图模型字段不完整")
            print("[FAIL] 页面视图模型未通过")
        else:
            print("[PASS] 页面视图模型通过")

    except Exception as exc:
        session.rollback()
        failures.append(str(exc))
        print(f"[FAIL] 数据验收异常：{exc}")
    finally:
        try:
            _cleanup(session, ids)
            print("[PASS] 测试数据清理通过")
        except Exception as exc:
            session.rollback()
            failures.append(f"清理失败：{exc}")
            print(f"[FAIL] 测试数据清理失败：{exc}")
        session.close()
    return failures


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    print("=" * 60)
    print("增强阶段5 运营看板验收")
    print("=" * 60)

    failures: list[str] = []
    failures.extend(check_imports())
    failures.extend(run_data_checks())

    print("-" * 60)
    if failures:
        print(f"[FAIL] 失败项：{'; '.join(failures)}")
        for item in failures:
            print(f"失败原因：{item}")
        return 1

    print("[PASS] 阶段5运营看板验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
