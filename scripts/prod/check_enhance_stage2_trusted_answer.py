#!/usr/bin/env python
"""生产 V1 增强阶段 2：可信回答 + 置信度 + 来源体系验收脚本。

检查 TrustedAnswerService 纯函数、question_log 字段写入与 Repository 能力。
不强制依赖 LLM / Qdrant / uvicorn；环境可用时可做可选集成验证。
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.models.question_log import QuestionLog
from app.repositories.question_repository import QuestionRepository
from app.services.trusted_answer_service import PrimarySource, TrustedAnswerService

DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段2 可信回答验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="可选环境变量文件路径")
    return parser.parse_args()


def _primary(**kwargs) -> PrimarySource:
    defaults = {
        "card_id": 101,
        "title": "合同审批流找不到审批人处理办法",
        "score": 0.91,
        "system_name": "合同系统",
        "module_name": "审批流",
        "confidence_level": "high",
    }
    defaults.update(kwargs)
    return PrimarySource(**defaults)


def check_trusted_answer_service() -> list[str]:
    """检查 TrustedAnswerService 导入与三类置信度答案格式。"""
    failures: list[str] = []
    try:
        svc = TrustedAnswerService()
        _ = svc  # 确认可实例化
        print("[PASS] TrustedAnswerService 导入通过")
    except Exception as exc:
        failures.append(f"TrustedAnswerService 导入失败：{exc}")
        print(f"[FAIL] TrustedAnswerService 导入失败：{exc}")
        return failures

    svc = TrustedAnswerService()
    high_answer = svc.build_trusted_answer(
        raw_answer="请先检查审批流配置是否正确。",
        confidence_level="high",
        primary_source=_primary(confidence_level="high"),
        matched=True,
    )
    high_required = ["【数字员工回答】", "【参考知识】", "知识卡片", "命中相似度", "可信度", "【反馈】"]
    if all(marker in high_answer for marker in high_required):
        print("[PASS] 高置信度可信回答格式通过")
    else:
        missing = [m for m in high_required if m not in high_answer]
        failures.append(f"高置信度答案缺少：{', '.join(missing)}")
        print(f"[FAIL] 高置信度可信回答格式未通过：缺少 {', '.join(missing)}")

    medium_answer = svc.build_trusted_answer(
        raw_answer="建议检查审批节点配置。",
        confidence_level="medium",
        primary_source=_primary(score=0.80, confidence_level="medium"),
        matched=True,
    )
    if "【提示】" in medium_answer and "人工确认" in medium_answer:
        print("[PASS] 中置信度可信回答格式通过")
    else:
        failures.append("中置信度答案缺少人工确认提示")
        print("[FAIL] 中置信度可信回答格式未通过")

    low_answer = svc.build_trusted_answer(
        raw_answer="不应展示的原始答案",
        confidence_level="low",
        primary_source=_primary(score=0.60, confidence_level="low"),
        matched=False,
    )
    if "【参考知识】" not in low_answer and "知识卡片" not in low_answer:
        print("[PASS] 低置信度拒答格式通过")
    else:
        failures.append("低置信度答案包含虚假来源")
        print("[FAIL] 低置信度拒答格式未通过：包含虚假来源")

    return failures


def check_question_log_write() -> list[str]:
    """检查 question_log 可信回答字段可写入。"""
    failures: list[str] = []
    session = SessionLocal()
    marker = f"__stage2_check_{uuid.uuid4().hex[:8]}__"
    try:
        repo = QuestionRepository(session)
        log = QuestionLog(
            request_id=uuid.uuid4().hex,
            question_raw=marker,
            question_masked=marker,
            rewritten_question=marker,
            user_id="__stage2_check__",
            group_id="__stage2_group__",
            source_type="stage2_check",
            intent="question",
            matched=1,
            primary_matched_card_id=101,
            primary_matched_card_title="测试知识卡片",
            confidence_level="high",
            answer_status="hit",
            answer_source="qdrant_rag",
            system_name="合同系统",
            module_name="审批流",
            answer="【数字员工回答】测试",
        )
        created = repo.create_log(log)
        session.commit()

        saved = repo.get_log_by_id(created.id)
        if saved is None:
            failures.append("question_log 写入后无法读取")
            print("[FAIL] question_log 可信回答字段写入未通过")
            return failures

        checks = {
            "primary_matched_card_id": 101,
            "primary_matched_card_title": "测试知识卡片",
            "confidence_level": "high",
            "answer_status": "hit",
            "answer_source": "qdrant_rag",
            "system_name": "合同系统",
            "module_name": "审批流",
        }
        for field, expected in checks.items():
            actual = getattr(saved, field, None)
            if actual != expected:
                failures.append(f"question_log.{field} 期望 {expected}，实际 {actual}")

        repo.update_trusted_answer_fields(
            created.id,
            primary_matched_card_id=102,
            primary_matched_card_title="更新后标题",
            confidence_level="medium",
            answer_status="medium_confidence",
            answer_source="qdrant_rag",
            system_name="ERP",
            module_name="权限",
        )
        session.commit()
        updated = repo.get_log_by_id(created.id)
        if updated and updated.answer_status == "medium_confidence":
            print("[PASS] question_log 可信回答字段写入通过")
        else:
            failures.append("update_trusted_answer_fields 回填失败")
            print("[FAIL] question_log 可信回答字段写入未通过")

        # 清理测试数据
        session.delete(saved)
        session.commit()
    except Exception as exc:
        session.rollback()
        failures.append(f"question_log 写入异常：{exc}")
        print(f"[FAIL] question_log 可信回答字段写入失败：{exc}")
        print(f"失败原因：{exc}")
    finally:
        session.close()

    return failures


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    print("=" * 60)
    print("增强阶段2 可信回答 + 置信度 + 来源体系验收")
    print("=" * 60)

    failures = check_trusted_answer_service()
    failures.extend(check_question_log_write())

    print("-" * 60)
    if failures:
        print(f"[FAIL] 失败项：{'; '.join(failures)}")
        for item in failures:
            print(f"失败原因：{item}")
        return 1

    print("[PASS] 阶段2可信回答验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
