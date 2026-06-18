#!/usr/bin/env python
"""生产 V1 增强阶段 3：知识卡片重复检测验收脚本。

检查 DuplicateCheckService 纯函数、Repository、日志写入与路由导入。
Qdrant / embedding 环境不足时跳过真实检测，但必须项仍须通过。
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
from app.infra.embedding_client import EmbeddingClientError
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.rag.qdrant_vector_store import QdrantVectorStoreError
from app.repositories.knowledge_duplicate_check_repository import KnowledgeDuplicateCheckRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.services.duplicate_check_service import DuplicateCheckError, DuplicateCheckService

DEFAULT_ENV_FILE = "docs/prod/.env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段3 重复检测验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE, help="可选环境变量文件路径")
    return parser.parse_args()


def check_classify_score() -> list[str]:
    """检查相似度等级分类。"""
    failures: list[str] = []
    svc = DuplicateCheckService(SessionLocal())
    cases = [
        (0.95, "high_duplicate"),
        (0.88, "suspected_duplicate"),
        (0.80, "related"),
        (0.60, "none"),
    ]
    for score, expected in cases:
        level, _, _ = svc.classify_score(score)
        if level != expected:
            failures.append(f"classify_score({score}) 期望 {expected}，实际 {level}")
    if failures:
        print(f"[FAIL] 相似度等级分类未通过：{'; '.join(failures)}")
    else:
        print("[PASS] 相似度等级分类通过")
    return failures


def check_build_check_text() -> list[str]:
    """检查检测文本拼接。"""
    failures: list[str] = []
    session = SessionLocal()
    try:
        svc = DuplicateCheckService(session)
        card = KnowledgeCard(
            title="合同审批人为空",
            question="审批人为空怎么办？",
            answer="检查审批流配置",
            system_name="合同系统",
            module_name="审批流",
        )
        text = svc.build_check_text(card)
        required = ["标题", "问题", "答案", "系统", "模块"]
        missing = [k for k in required if k not in text]
        if missing:
            failures.append(f"检测文本缺少字段：{', '.join(missing)}")
            print(f"[FAIL] 检测文本拼接未通过：缺少 {', '.join(missing)}")
        else:
            print("[PASS] 检测文本拼接通过")
    finally:
        session.close()
    return failures


def check_candidate_query() -> list[str]:
    """检查候选知识查询。"""
    failures: list[str] = []
    session = SessionLocal()
    try:
        repo = KnowledgeRepository(session)
        _ = repo.list_duplicate_candidates()
        print("[PASS] 候选知识查询通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 候选知识查询失败：{exc}")
    finally:
        session.close()
    return failures


def check_log_write() -> list[str]:
    """检查重复检测日志写入与清理。"""
    failures: list[str] = []
    session = SessionLocal()
    marker = f"__stage3_check_{uuid.uuid4().hex[:8]}__"
    try:
        repo = KnowledgeDuplicateCheckRepository(session)
        logs = [
            KnowledgeDuplicateCheckLog(
                source_card_id=999001,
                source_type=marker,
                candidate_card_id=None,
                check_level="none",
                check_result="no_duplicate",
                operator_user="__stage3_check__",
            )
        ]
        repo.create_many(logs)
        session.commit()

        recent = repo.list_recent(limit=5)
        if not any(log.source_type == marker for log in recent):
            failures.append("写入后无法查询到测试日志")
            print("[FAIL] 重复检测日志写入未通过")
        else:
            print("[PASS] 重复检测日志写入通过")

        from sqlalchemy import select

        for log in session.scalars(
            select(KnowledgeDuplicateCheckLog).where(KnowledgeDuplicateCheckLog.source_type == marker)
        ).all():
            session.delete(log)
        session.commit()
    except Exception as exc:
        session.rollback()
        failures.append(str(exc))
        print(f"[FAIL] 重复检测日志写入失败：{exc}")
    finally:
        session.close()
    return failures


def check_router_import() -> list[str]:
    """检查手动检测路由可导入。"""
    failures: list[str] = []
    try:
        from app.routers.knowledge_router import check_duplicate_knowledge_card

        _ = check_duplicate_knowledge_card
        print("[PASS] 路由导入通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 路由导入失败：{exc}")
    return failures


def check_deposit_path_integration() -> list[str]:
    """检查企微沉淀 create_pending_knowledge 已接入 DuplicateCheckService。"""
    failures: list[str] = []
    try:
        import inspect

        from app.graphs import knowledge_deposit_graph as deposit_mod

        source = inspect.getsource(deposit_mod.create_pending_knowledge)
        if "DuplicateCheckService" not in source:
            failures.append("create_pending_knowledge 未引用 DuplicateCheckService")
        if "check_card_object_async" not in source:
            failures.append("create_pending_knowledge 未使用 check_card_object_async")
        if 'source_type="user_deposit"' not in source and "source_type='user_deposit'" not in source:
            failures.append("create_pending_knowledge 未使用 source_type=user_deposit")
        if "DuplicateCheckError" not in source:
            failures.append("create_pending_knowledge 未处理 DuplicateCheckError")
        if failures:
            print(f"[FAIL] 企微沉淀路径接入检查未通过：{'; '.join(failures)}")
        else:
            print("[PASS] 企微沉淀路径 DuplicateCheckService 接入检查通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 企微沉淀路径接入检查失败：{exc}")
    return failures


def check_user_deposit_log_write() -> list[str]:
    """检查 source_type=user_deposit 的重复检测日志可写入。"""
    failures: list[str] = []
    session = SessionLocal()
    marker = f"__stage3_deposit_{uuid.uuid4().hex[:8]}__"
    try:
        repo = KnowledgeDuplicateCheckRepository(session)
        logs = [
            KnowledgeDuplicateCheckLog(
                source_card_id=999002,
                source_type="user_deposit",
                candidate_card_id=None,
                check_level="none",
                check_result="no_duplicate",
                operator_user=marker,
            )
        ]
        repo.create_many(logs)
        session.commit()

        from sqlalchemy import select

        rows = list(
            session.scalars(
                select(KnowledgeDuplicateCheckLog).where(
                    KnowledgeDuplicateCheckLog.operator_user == marker,
                    KnowledgeDuplicateCheckLog.source_type == "user_deposit",
                )
            ).all()
        )
        if not rows:
            failures.append("user_deposit 日志写入后无法查询")
            print("[FAIL] user_deposit 日志写入验证未通过")
        else:
            print("[PASS] user_deposit 日志写入验证通过")

        for log in rows:
            session.delete(log)
        session.commit()
    except Exception as exc:
        session.rollback()
        failures.append(str(exc))
        print(f"[FAIL] user_deposit 日志写入验证失败：{exc}")
    finally:
        session.close()
    return failures


def check_old_duplicate_check_not_blocking() -> list[str]:
    """检查旧 duplicate_check 节点不再强阻断（方案 A）。"""
    failures: list[str] = []
    try:
        import inspect

        from app.graphs import knowledge_deposit_graph as deposit_mod

        dup_source = inspect.getsource(deposit_mod.duplicate_check)
        route_source = inspect.getsource(deposit_mod.route_after_duplicate)
        if 'state["status"] = "duplicate_suspected"' in dup_source:
            failures.append("duplicate_check 仍会设置 duplicate_suspected 阻断状态")
        if "pre_check_only" not in dup_source:
            failures.append("duplicate_check 未标记 pre_check_only")
        if 'return "reply"' in route_source and "duplicate_suspected" in route_source:
            failures.append("route_after_duplicate 仍会因 duplicate_suspected 提前 reply")
        if failures:
            print(f"[FAIL] 旧 duplicate_check 职责边界检查未通过：{'; '.join(failures)}")
        else:
            print("[PASS] 旧 duplicate_check 仅预检不阻断（方案 A）")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 旧 duplicate_check 职责边界检查失败：{exc}")
    return failures


DEPOSIT_FULL_CARD = """标题：Stage3验收专用-工单流转异常排查{suffix}
问题：Stage3验收{suffix}时遇到工单状态卡在待审批应如何排查？
答案：先确认工单当前审批节点与审批人配置是否正确，再检查流程引擎日志与权限映射是否一致。
系统：数字员工助手
模块：工单管理
标签：验收,工单,Stage3,{suffix}
场景：工单审批卡住无法流转
原因分析：常见原因是审批人离职、节点配置错误或流程版本未同步。
排查步骤：
1. 在工单详情页查看当前节点与待办审批人
2. 核对流程定义中该节点的审批角色配置
3. 检查审批人账号状态与组织权限
4. 必要时由管理员重新指派审批人后重试流转
解决方案：修正审批人配置或回退到上一节点后重新提交，并在变更单记录处理过程。
风险提示：禁止直接修改生产流程引擎数据库表，应通过标准配置界面操作。
来源群：验收测试群-{suffix}
来源人：check-script"""

MAX_DEPOSIT_ATTEMPTS = 3


async def check_deposit_graph_flow_async() -> list[str]:
    """真实企微模拟沉淀：CommandRouter → graph → create_pending_knowledge → 写日志。"""
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    group_id = f"stage3-deposit-{suffix}"
    user_id = f"stage3-user-{suffix}"

    from unittest.mock import patch

    from sqlalchemy import select

    from app.models.knowledge_contribution import KnowledgeContribution
    from app.schemas.wecom_message_schema import WeComMessage
    from app.services.deposit_session_service import DepositSessionService
    from app.services.knowledge_deposit_check_service import AiCheckResult, KnowledgeDepositCheckService
    from app.wecom.command_router import CommandRouter

    async def _ai_quality_pass(_self, _parsed_card: dict) -> AiCheckResult:
        return AiCheckResult(passed=True, score=0.95, reason="stage3 acceptance bypass")

    def make_msg(content: str) -> WeComMessage:
        return WeComMessage(
            message_id=str(uuid.uuid4()),
            group_id=group_id,
            user_id=user_id,
            user_name="Stage3验收脚本",
            content=content,
        )

    card_id: int | None = None
    contribution_id: str | None = None

    try:
        with patch.object(KnowledgeDepositCheckService, "ai_quality_check", _ai_quality_pass):
            with SessionLocal() as db:
                router = CommandRouter(db)
                session_svc = DepositSessionService()

                await router.route(make_msg("【沉淀】"))
                if not await session_svc.is_active(make_msg("")):
                    failures.append("【沉淀】后 session 未激活")
                    print("[FAIL] 企微沉淀 graph 流程：session 未激活")
                    return failures

                full_card = DEPOSIT_FULL_CARD.format(suffix=suffix)
                submit_resp = None
                for _attempt in range(1, MAX_DEPOSIT_ATTEMPTS + 1):
                    await router.route(make_msg("【沉淀】"))
                    submit_resp = await router.route(make_msg(full_card))
                    if submit_resp.status == "pending_card_created" and submit_resp.knowledge_card_id:
                        break
                    contribution_id = submit_resp.contribution_id or contribution_id

                if submit_resp is None or submit_resp.status != "pending_card_created":
                    status = getattr(submit_resp, "status", None)
                    failures.append(f"期望 pending_card_created，实际 {status}")
                    print(f"[FAIL] 企微沉淀 graph 流程：status={status}")
                    return failures

                card_id = submit_resp.knowledge_card_id
                contribution_id = submit_resp.contribution_id
                if not card_id:
                    failures.append("未返回 knowledge_card_id")
                    print("[FAIL] 企微沉淀 graph 流程：无 knowledge_card_id")
                    return failures

                card = db.get(KnowledgeCard, card_id)
                if card is None or card.audit_status != "pending":
                    failures.append(f"卡片 {card_id} 非 pending 状态")
                    print(f"[FAIL] 企微沉淀 graph 流程：卡片 audit_status={getattr(card, 'audit_status', None)}")

                log_rows = list(
                    db.scalars(
                        select(KnowledgeDuplicateCheckLog).where(
                            KnowledgeDuplicateCheckLog.source_card_id == card_id,
                            KnowledgeDuplicateCheckLog.source_type == "user_deposit",
                        )
                    ).all()
                )
                if not log_rows:
                    failures.append(f"card_id={card_id} 无 user_deposit 重复检测日志")
                    print("[FAIL] 企微沉淀 graph 流程：未写入 user_deposit 日志")
                else:
                    print(f"[PASS] 企微沉淀 graph 流程：user_deposit 日志 {len(log_rows)} 条")

                if contribution_id:
                    contrib = db.scalars(
                        select(KnowledgeContribution).where(
                            KnowledgeContribution.contribution_id == contribution_id
                        )
                    ).first()
                    if contrib is None:
                        failures.append(f"未找到 contribution {contribution_id}")
                        print("[FAIL] 企微沉淀 graph 流程：contribution 不存在")
                    else:
                        dup_json = contrib.duplicate_result_json or ""
                        if "duplicate_check_service" not in dup_json:
                            failures.append("contribution.duplicate_result_json 缺少 duplicate_check_service")
                            print("[FAIL] 企微沉淀 graph 流程：duplicate_result_json 未写入检测结果")
                        elif "null" in dup_json.split("duplicate_check_service")[-1][:20]:
                            failures.append("duplicate_check_service 为空")
                            print("[FAIL] 企微沉淀 graph 流程：duplicate_check_service 为空")
                        else:
                            print("[PASS] 企微沉淀 graph 流程：duplicate_result_json 已写入")

                if not failures:
                    print("[PASS] 企微沉淀 graph 真实流程验收通过")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 企微沉淀 graph 流程异常：{exc}")
    finally:
        cleanup_session = SessionLocal()
        try:
            from sqlalchemy import select

            if card_id is not None:
                for log in cleanup_session.scalars(
                    select(KnowledgeDuplicateCheckLog).where(
                        KnowledgeDuplicateCheckLog.source_card_id == card_id
                    )
                ).all():
                    cleanup_session.delete(log)
                card = cleanup_session.get(KnowledgeCard, card_id)
                if card is not None:
                    cleanup_session.delete(card)
            if contribution_id:
                from app.models.knowledge_contribution import KnowledgeContribution

                contrib = cleanup_session.scalars(
                    select(KnowledgeContribution).where(
                        KnowledgeContribution.contribution_id == contribution_id
                    )
                ).first()
                if contrib is not None:
                    cleanup_session.delete(contrib)
            cleanup_session.commit()
        except Exception:
            cleanup_session.rollback()
        finally:
            cleanup_session.close()

    return failures


async def check_deposit_duplicate_failure_async() -> list[str]:
    """失败路径：DuplicateCheckService 异常时不进入 pending。"""
    failures: list[str] = []
    suffix = uuid.uuid4().hex[:8]
    group_id = f"stage3-fail-{suffix}"
    user_id = f"stage3-fail-user-{suffix}"

    from unittest.mock import patch

    from app.schemas.wecom_message_schema import WeComMessage
    from app.services.deposit_session_service import DepositSessionService
    from app.services.duplicate_check_service import DuplicateCheckError, DuplicateCheckService
    from app.services.knowledge_deposit_check_service import AiCheckResult, KnowledgeDepositCheckService
    from app.wecom.command_router import CommandRouter

    async def _ai_quality_pass(_self, _parsed_card: dict) -> AiCheckResult:
        return AiCheckResult(passed=True, score=0.95, reason="stage3 acceptance bypass")

    async def _duplicate_fail(_self, _card, **kwargs):
        raise DuplicateCheckError("stage3 acceptance injected failure")

    def make_msg(content: str) -> WeComMessage:
        return WeComMessage(
            message_id=str(uuid.uuid4()),
            group_id=group_id,
            user_id=user_id,
            user_name="Stage3验收脚本",
            content=content,
        )

    contribution_id: str | None = None

    try:
        with patch.object(KnowledgeDepositCheckService, "ai_quality_check", _ai_quality_pass):
            with patch.object(DuplicateCheckService, "check_card_object_async", _duplicate_fail):
                with SessionLocal() as db:
                    router = CommandRouter(db)
                    await router.route(make_msg("【沉淀】"))
                    resp = await router.route(make_msg(DEPOSIT_FULL_CARD.format(suffix=suffix)))
                    contribution_id = resp.contribution_id

                    if resp.status != "duplicate_check_failed":
                        failures.append(f"期望 duplicate_check_failed，实际 {resp.status}")
                        print(f"[FAIL] 企微沉淀失败路径：status={resp.status}")
                    elif resp.knowledge_card_id:
                        failures.append("失败路径不应生成 knowledge_card_id")
                        print("[FAIL] 企微沉淀失败路径：不应生成 pending 卡片")
                    else:
                        print("[PASS] 企微沉淀失败路径：未进入 pending 且返回 duplicate_check_failed")
    except Exception as exc:
        failures.append(str(exc))
        print(f"[FAIL] 企微沉淀失败路径异常：{exc}")
    finally:
        if contribution_id:
            cleanup_session = SessionLocal()
            try:
                from sqlalchemy import select

                from app.models.knowledge_contribution import KnowledgeContribution

                contrib = cleanup_session.scalars(
                    select(KnowledgeContribution).where(
                        KnowledgeContribution.contribution_id == contribution_id
                    )
                ).first()
                if contrib is not None:
                    cleanup_session.delete(contrib)
                cleanup_session.commit()
            except Exception:
                cleanup_session.rollback()
            finally:
                cleanup_session.close()

    return failures


def check_deposit_graph_flow() -> list[str]:
    """同步包装：运行企微沉淀真实流程验收。"""
    import asyncio

    try:
        return asyncio.run(check_deposit_graph_flow_async())
    except Exception as exc:
        print(f"[FAIL] 企微沉淀 graph 流程启动失败：{exc}")
        return [str(exc)]


def check_deposit_duplicate_failure() -> list[str]:
    """同步包装：运行企微沉淀重复检测失败路径验收。"""
    import asyncio

    try:
        return asyncio.run(check_deposit_duplicate_failure_async())
    except Exception as exc:
        print(f"[FAIL] 企微沉淀失败路径启动失败：{exc}")
        return [str(exc)]


def check_real_qdrant() -> list[str]:
    """可选：执行一次真实 Qdrant 重复检测。"""
    failures: list[str] = []
    session = SessionLocal()
    try:
        repo = KnowledgeRepository(session)
        card = repo.list_duplicate_candidates()
        if not card:
            print("[SKIP] Qdrant 环境不足，跳过真实检测（无候选卡片）")
            return failures
        svc = DuplicateCheckService(session)
        target = card[0]
        svc.check_card_object(
            target,
            operator_user="__stage3_check__",
            source_type="__stage3_real_check__",
        )
        session.commit()
        print("[PASS] 真实 Qdrant 检测通过")

        from sqlalchemy import select

        for log in session.scalars(
            select(KnowledgeDuplicateCheckLog).where(
                KnowledgeDuplicateCheckLog.source_type == "__stage3_real_check__"
            )
        ).all():
            session.delete(log)
        session.commit()
    except (DuplicateCheckError, EmbeddingClientError, QdrantVectorStoreError) as exc:
        print(f"[SKIP] Qdrant 环境不足，跳过真实检测：{exc}")
    except Exception as exc:
        failures.append(f"真实检测异常：{exc}")
        print(f"[FAIL] 真实 Qdrant 检测失败：{exc}")
    finally:
        session.close()
    return failures


def main() -> int:
    args = parse_args()
    if args.env_file:
        apply_env_file(args.env_file)

    print("=" * 60)
    print("增强阶段3 知识卡片重复检测验收")
    print("=" * 60)

    failures: list[str] = []

    try:
        _ = DuplicateCheckService(SessionLocal())
        print("[PASS] DuplicateCheckService 导入通过")
    except Exception as exc:
        failures.append(f"导入失败：{exc}")
        print(f"[FAIL] DuplicateCheckService 导入失败：{exc}")

    failures.extend(check_classify_score())
    failures.extend(check_build_check_text())
    failures.extend(check_candidate_query())
    failures.extend(check_log_write())
    failures.extend(check_router_import())
    failures.extend(check_deposit_path_integration())
    failures.extend(check_old_duplicate_check_not_blocking())
    failures.extend(check_user_deposit_log_write())
    failures.extend(check_deposit_graph_flow())
    failures.extend(check_deposit_duplicate_failure())
    failures.extend(check_real_qdrant())

    print("-" * 60)
    if failures:
        print(f"[FAIL] 失败项：{'; '.join(failures)}")
        for item in failures:
            print(f"失败原因：{item}")
        return 1

    print("[PASS] 阶段3重复检测验收通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
