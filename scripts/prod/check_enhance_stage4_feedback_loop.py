#!/usr/bin/env python
"""生产 V1 增强阶段 4：反馈闭环 MVP 验收脚本。"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import delete, select

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.feedback_log import FeedbackLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_card_revision import KnowledgeCardRevision
from app.models.question_log import QuestionLog
from app.schemas.feedback_schema import FeedbackSubmitRequest
from app.services.feedback_evolution_service import FeedbackEvolutionError, FeedbackEvolutionService

DEFAULT_ENV_FILE = "docs/prod/.env"
MARKER = "__stage4_feedback_check__"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段4 反馈闭环验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def check_parse_text() -> list[str]:
    failures: list[str] = []
    svc = FeedbackEvolutionService(SessionLocal())
    cases = [
        ("有用", "useful"),
        ("已解决", "useful"),
        ("无用：步骤不完整", "useless"),
        ("答非所问", "useless"),
        ("补充：正确答案示例", "supplement"),
        ("纠错：正确答案示例", "supplement"),
    ]
    for text, expected in cases:
        parsed = svc.parse_text_feedback(text)
        if parsed is None or parsed.feedback_type != expected:
            failures.append(f"无法识别：{text}")
    if failures:
        print(f"[FAIL] 文本反馈指令解析未通过：{'; '.join(failures)}")
    else:
        print("[PASS] 文本反馈指令解析通过")
    return failures


def check_no_recent_question() -> list[str]:
    failures: list[str] = []
    session = SessionLocal()
    try:
        svc = FeedbackEvolutionService(session)
        try:
            svc.submit_feedback(
                FeedbackSubmitRequest(
                    user_id=f"{MARKER}_no_log",
                    group_id=f"{MARKER}_group",
                    feedback_type="useful",
                )
            )
            failures.append("无最近问答时应失败")
            print("[FAIL] 最近问答绑定规则未通过：无日志时未报错")
        except FeedbackEvolutionError as exc:
            if "未找到可绑定" not in exc.message:
                failures.append(exc.message)
                print(f"[FAIL] 最近问答绑定规则：错误信息不符合预期：{exc.message}")
            else:
                print("[PASS] 最近问答绑定规则通过")
    finally:
        session.close()
    return failures


def _cleanup(session, *, card_id: int | None, log_id: int | None) -> None:
    if log_id is not None:
        fb_ids = list(
            session.scalars(select(FeedbackLog.id).where(FeedbackLog.question_log_id == log_id)).all()
        )
        if fb_ids:
            session.execute(
                delete(KnowledgeCardRevision).where(
                    KnowledgeCardRevision.source_feedback_id.in_(fb_ids)
                )
            )
        session.execute(delete(FeedbackLog).where(FeedbackLog.question_log_id == log_id))
        session.execute(delete(QuestionLog).where(QuestionLog.id == log_id))
    if card_id is not None:
        session.execute(delete(KnowledgeCard).where(KnowledgeCard.id == card_id))
    session.commit()


def check_feedback_flows() -> list[str]:
    failures: list[str] = []
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user_id = f"{MARKER}_{suffix}"
    group_id = f"{MARKER}_group_{suffix}"
    card_id: int | None = None
    log_id: int | None = None

    try:
        card = KnowledgeCard(
            title=f"{MARKER} 测试卡片 {suffix}",
            question="测试问题",
            answer="测试答案",
            audit_status="approved",
            enabled=1,
            deleted=0,
            useful_count=0,
            useless_count=0,
            supplement_count=0,
            vector_status="success",
        )
        session.add(card)
        session.flush()
        card_id = card.id

        log = QuestionLog(
            request_id=f"{MARKER}-{suffix}",
            question_raw=f"{MARKER} 提问",
            question_masked=f"{MARKER} 提问",
            rewritten_question=f"{MARKER} 提问",
            user_id=user_id,
            group_id=group_id,
            source_type=MARKER,
            intent="question",
            matched=1,
            primary_matched_card_id=card_id,
            primary_matched_card_title=card.title,
            confidence_level="high",
            answer_status="hit",
            answer_source="qdrant_rag",
            answer="测试回答",
        )
        session.add(log)
        session.flush()
        log_id = log.id
        session.commit()

        svc = FeedbackEvolutionService(session)

        useful = svc.submit_feedback(
            FeedbackSubmitRequest(user_id=user_id, group_id=group_id, feedback_type="useful")
        )
        session.refresh(card)
        if useful.feedback_type != "useful" or card.useful_count != 1:
            failures.append("useful 反馈或 useful_count 异常")
            print("[FAIL] 有用反馈写入未通过")
        else:
            print("[PASS] 有用反馈写入通过")

        useless = svc.submit_feedback(
            FeedbackSubmitRequest(
                user_id=user_id,
                group_id=group_id,
                feedback_type="useless",
                reason_text="步骤不完整",
            )
        )
        session.refresh(card)
        if useless.feedback_type != "useless" or card.useless_count != 1:
            failures.append("useless 反馈或 useless_count 异常")
            print("[FAIL] 无用反馈写入未通过")
        else:
            print("[PASS] 无用反馈写入通过")

        if card.quality_score is None or float(card.quality_score) != 0.5:
            failures.append(f"quality_score 期望 0.5，实际 {card.quality_score}")
            print(f"[FAIL] 知识卡片质量计数更新未通过：quality_score={card.quality_score}")
        else:
            print("[PASS] 知识卡片质量计数更新通过")

        supplement = svc.submit_feedback(
            FeedbackSubmitRequest(
                user_id=user_id,
                group_id=group_id,
                feedback_type="supplement",
                supplement_text="补充后的正确答案内容",
            )
        )
        session.refresh(card)
        revision = session.scalar(
            select(KnowledgeCardRevision).where(KnowledgeCardRevision.id == supplement.revision_id)
        )
        if supplement.revision_id is None or revision is None:
            failures.append("未生成 knowledge_card_revision")
            print("[FAIL] 补充反馈生成修订建议未通过")
        elif card.supplement_count != 1:
            failures.append("supplement_count 未更新")
            print("[FAIL] 补充反馈 supplement_count 未更新")
        elif revision.revision_type != "update_existing" or revision.original_card_id != card_id:
            failures.append("revision 字段不符合 update_existing 规则")
            print("[FAIL] 补充反馈 revision 规则未通过")
        else:
            print("[PASS] 补充反馈生成修订建议通过")

        fb_rows = list(
            session.scalars(select(FeedbackLog).where(FeedbackLog.question_log_id == log_id)).all()
        )
        if len(fb_rows) < 3:
            failures.append(f"feedback_log 记录数不足：{len(fb_rows)}")
            print(f"[FAIL] feedback_log 写入不足：{len(fb_rows)} 条")
        session.commit()
    except Exception as exc:
        session.rollback()
        failures.append(str(exc))
        print(f"[FAIL] 反馈流程异常：{exc}")
    finally:
        try:
            _cleanup(session, card_id=card_id, log_id=log_id)
        except Exception:
            session.rollback()
        session.close()

    return failures


def check_supplement_empty() -> list[str]:
    failures: list[str] = []
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user_id = f"{MARKER}_sup_{suffix}"
    group_id = f"{MARKER}_group_{suffix}"
    log_id: int | None = None
    try:
        log = QuestionLog(
            request_id=f"{MARKER}-sup-{suffix}",
            question_raw="补充测试",
            question_masked="补充测试",
            rewritten_question="补充测试",
            user_id=user_id,
            group_id=group_id,
            source_type=MARKER,
            intent="question",
            matched=0,
            answer_status="miss",
            answer="未命中",
        )
        session.add(log)
        session.flush()
        log_id = log.id
        session.commit()

        svc = FeedbackEvolutionService(session)
        try:
            svc.submit_feedback(
                FeedbackSubmitRequest(
                    user_id=user_id,
                    group_id=group_id,
                    feedback_type="supplement",
                    supplement_text="",
                )
            )
            failures.append("空 supplement_text 应失败")
            print("[FAIL] 空补充内容应返回明确提示")
        except FeedbackEvolutionError as exc:
            if "补充" not in exc.message:
                failures.append(exc.message)
                print(f"[FAIL] 空补充内容提示不符合预期：{exc.message}")
            else:
                print("[PASS] 空补充内容校验通过")
    finally:
        if log_id is not None:
            session.execute(delete(QuestionLog).where(QuestionLog.id == log_id))
            session.commit()
        session.close()
    return failures


def check_router_import() -> list[str]:
    failures: list[str] = []
    try:
        from app.routers.feedback_router import get_feedback, list_feedback, submit_feedback

        _ = submit_feedback, list_feedback, get_feedback
        print("[PASS] API 路由导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] API 路由导入失败：{exc}")
    return failures


def check_wecom_feedback_parse() -> list[str]:
    failures: list[str] = []
    try:
        from app.wecom.command_router import CommandRouter

        _ = CommandRouter
        if not FeedbackEvolutionService.is_feedback_text("有用"):
            failures.append("CommandRouter 依赖的 is_feedback_text 不可用")
            print("[FAIL] mock wecom 文本反馈识别未通过")
        else:
            print("[PASS] mock wecom 文本反馈识别通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] mock wecom 文本反馈识别失败：{exc}")
    return failures


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    print("=" * 60)
    print("增强阶段4 反馈闭环 MVP 验收")
    print("=" * 60)

    failures: list[str] = []

    try:
        _ = FeedbackEvolutionService(SessionLocal())
        print("[PASS] FeedbackEvolutionService 导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] FeedbackEvolutionService 导入失败：{exc}")

    failures.extend(check_parse_text())
    failures.extend(check_no_recent_question())
    failures.extend(check_feedback_flows())
    failures.extend(check_supplement_empty())
    failures.extend(check_router_import())
    failures.extend(check_wecom_feedback_parse())

    print("-" * 60)
    if failures:
        print(f"[FAIL] 失败项：{'; '.join(failures)}")
        for item in failures:
            print(f"失败原因：{item}")
        return 1

    print("[PASS] 阶段4反馈闭环验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
