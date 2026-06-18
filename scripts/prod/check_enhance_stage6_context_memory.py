#!/usr/bin/env python
"""生产 V1 增强阶段 6：多轮追问 + 30 天轻量记忆验收脚本。"""

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

from app.agent.ask_state import AskState
from app.core.settings import apply_env_file
from app.db.database import SessionLocal
from app.infra.redis_client import RedisClientError
from app.models.question_log import QuestionLog
from app.repositories.question_repository import QuestionRepository
from app.schemas.context_schema import ConversationContext
from app.services.ask_log_service import AskLogService
from app.services.context_enhance_service import (
    CONTEXT_SOURCE_MODULES,
    CONTEXT_SOURCE_NONE,
    CONTEXT_SOURCE_REDIS,
    ContextEnhanceService,
)
from app.services.conversation_context_service import ConversationContextService

DEFAULT_ENV_FILE = "docs/prod/.env"
MARKER = "__stage6_context__"


class InMemoryConversationStore:
    """验收用内存 Redis 替身。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get_value(self, key: str) -> str | None:
        return self._data.get(key)

    async def set_value(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        _ = ttl_seconds
        self._data[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        if key in self._data:
            del self._data[key]
            return 1
        return 0


class BrokenConversationStore:
    """模拟 Redis 异常，用于降级验收。"""

    async def get_value(self, key: str) -> str | None:
        _ = key
        raise RedisClientError("mock redis unavailable")

    async def set_value(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        _ = (key, value, ttl_seconds)
        raise RedisClientError("mock redis unavailable")

    async def delete_key(self, key: str) -> int:
        _ = key
        raise RedisClientError("mock redis unavailable")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="增强阶段6 上下文增强与轻量记忆验收")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    return parser.parse_args()


def _fail(message: str) -> None:
    print(f"[FAIL] 失败项：{message.split('：', 1)[0] if '：' in message else message}")
    print(f"失败原因：{message}")


def check_imports() -> bool:
    ok = True
    try:
        from app.services.context_enhance_service import ContextEnhanceService as _  # noqa: F401

        print("[PASS] ContextEnhanceService 导入通过")
    except Exception as exc:
        ok = False
        _fail(f"ContextEnhanceService 导入：{exc}")

    try:
        from app.services.conversation_context_service import ConversationContextService as _  # noqa: F401

        print("[PASS] ConversationContextService 导入通过")
    except Exception as exc:
        ok = False
        _fail(f"ConversationContextService 导入：{exc}")

    try:
        from app.schemas.context_schema import ContextEnhanceResult as _  # noqa: F401

        print("[PASS] 上下文 Schema 导入通过")
    except Exception as exc:
        ok = False
        _fail(f"上下文 Schema 导入：{exc}")

    return ok


def check_follow_up_rules() -> bool:
    session = SessionLocal()
    try:
        svc = ContextEnhanceService(session, conversation_service=ConversationContextService(store=InMemoryConversationStore()))
        cases = ["那在哪里配置？", "还是不行怎么办？", "这个怎么操作？"]
        for text in cases:
            if not svc.is_follow_up_question(text):
                _fail(f"追问识别规则：未识别 {text}")
                return False
        print("[PASS] 追问识别规则通过")
        return True
    finally:
        session.close()


def check_explicit_business_rules() -> bool:
    session = SessionLocal()
    try:
        svc = ContextEnhanceService(session, conversation_service=ConversationContextService(store=InMemoryConversationStore()))
        cases = ["合同系统审批人在哪里配置？", "报销系统流程怎么设置？"]
        for text in cases:
            if not svc.has_explicit_business_context(text):
                _fail(f"明确业务问题识别：未识别 {text}")
                return False
        print("[PASS] 明确业务问题识别通过")
        return True
    finally:
        session.close()


async def _check_redis_roundtrip() -> bool:
    store = InMemoryConversationStore()
    svc = ConversationContextService(store=store)
    user_id = f"{MARKER}_user"
    group_id = f"{MARKER}_group"
    await svc.save_recent_context(
        user_id=user_id,
        group_id=group_id,
        question="合同审批流找不到审批人怎么办？",
        rewritten_question="合同审批流找不到审批人怎么办？",
        answer="需要检查审批流节点配置。",
        system_name="合同系统",
        module_name="审批流",
        primary_matched_card_id=1,
        primary_matched_card_title="测试卡片",
        confidence_level="high",
    )
    ctx = await svc.get_recent_context(user_id=user_id, group_id=group_id)
    if ctx is None or ctx.system_name != "合同系统":
        _fail("Redis 上下文保存读取：读取结果不符合预期")
        return False
    print("[PASS] Redis 上下文保存读取通过")
    return True


def check_redis_roundtrip() -> bool:
    import asyncio

    return asyncio.run(_check_redis_roundtrip())


def check_redis_rewrite() -> bool:
    import asyncio

    async def _run() -> bool:
        store = InMemoryConversationStore()
        conv_svc = ConversationContextService(store=store)
        user_id = f"{MARKER}_rewrite"
        group_id = f"{MARKER}_group"
        await conv_svc.save_recent_context(
            user_id=user_id,
            group_id=group_id,
            question="合同审批流找不到审批人怎么办？",
            rewritten_question="合同审批流找不到审批人怎么办？",
            answer="检查审批流节点配置。",
            system_name="合同系统",
            module_name="审批流",
            primary_matched_card_id=1,
            primary_matched_card_title="测试卡片",
            confidence_level="high",
        )
        session = SessionLocal()
        try:
            enhance_svc = ContextEnhanceService(session, conversation_service=conv_svc)
            result = await enhance_svc.enhance_question_async(
                question="那在哪里配置？",
                user_id=user_id,
                group_id=group_id,
            )
            if not result.used_context or result.context_source != CONTEXT_SOURCE_REDIS:
                _fail("Redis 上下文问题改写：未使用 redis_recent_turn")
                return False
            if "合同系统" not in result.rewritten_question or "审批流" not in result.rewritten_question:
                _fail("Redis 上下文问题改写：改写结果缺少上下文")
                return False
            print("[PASS] Redis 上下文问题改写通过")
            return True
        finally:
            session.close()

    return asyncio.run(_run())


def check_recent_modules_enhance() -> bool:
    import asyncio

    async def _run() -> bool:
        session = SessionLocal()
        suffix = uuid.uuid4().hex[:8]
        user_id = f"{MARKER}_modules_{suffix}"
        group_id = f"{MARKER}_group_{suffix}"
        log_ids: list[int] = []
        try:
            now = datetime.now()
            for _ in range(3):
                log = QuestionLog(
                    request_id=f"{MARKER}-{uuid.uuid4().hex}",
                    question_raw="历史问题",
                    question_masked="历史问题",
                    rewritten_question="历史问题",
                    user_id=user_id,
                    group_id=group_id,
                    source_type=MARKER,
                    intent="question",
                    matched=1,
                    confidence_level="high",
                    answer_status="hit",
                    system_name="合同系统",
                    module_name="审批流",
                    create_time=now,
                )
                session.add(log)
            session.commit()

            enhance_svc = ContextEnhanceService(
                session,
                conversation_service=ConversationContextService(store=InMemoryConversationStore()),
            )
            result = await enhance_svc.enhance_question_async(
                question="审批人在哪里设置？",
                user_id=user_id,
                group_id=group_id,
            )
            if not result.used_context or result.context_source != CONTEXT_SOURCE_MODULES:
                _fail("30 天常问系统/模块增强：未使用 user_recent_modules")
                return False
            if "合同系统" not in result.rewritten_question or "审批流" not in result.rewritten_question:
                _fail("30 天常问系统/模块增强：改写结果不符合预期")
                return False
            print("[PASS] 30 天常问系统/模块增强通过")
            return True
        finally:
            rows = session.scalars(select(QuestionLog.id).where(QuestionLog.user_id == user_id)).all()
            log_ids.extend(rows)
            if log_ids:
                session.execute(delete(QuestionLog).where(QuestionLog.id.in_(log_ids)))
                session.commit()
            session.close()

    return asyncio.run(_run())


def check_explicit_not_overwritten() -> bool:
    import asyncio

    async def _run() -> bool:
        store = InMemoryConversationStore()
        conv_svc = ConversationContextService(store=store)
        user_id = f"{MARKER}_explicit"
        group_id = f"{MARKER}_group"
        await conv_svc.save_recent_context(
            user_id=user_id,
            group_id=group_id,
            question="合同审批流找不到审批人怎么办？",
            rewritten_question="合同审批流找不到审批人怎么办？",
            answer="检查审批流节点配置。",
            system_name="合同系统",
            module_name="审批流",
            primary_matched_card_id=1,
            primary_matched_card_title="测试卡片",
            confidence_level="high",
        )
        session = SessionLocal()
        try:
            enhance_svc = ContextEnhanceService(session, conversation_service=conv_svc)
            question = "报销系统审批人在哪里配置？"
            result = await enhance_svc.enhance_question_async(
                question=question,
                user_id=user_id,
                group_id=group_id,
            )
            if result.used_context or result.rewritten_question != question:
                _fail("明确问题不被覆盖：明确系统问题被历史上下文改写")
                return False
            print("[PASS] 明确问题不被覆盖通过")
            return True
        finally:
            session.close()

    return asyncio.run(_run())


def check_question_log_fields() -> bool:
    session = SessionLocal()
    log_id: int | None = None
    try:
        state: AskState = {
            "question_raw": "那在哪里配置？",
            "original_question": "那在哪里配置？",
            "question_masked": "在合同系统的审批流场景下，继续追问：那在哪里配置？",
            "rewritten_question": "在合同系统的审批流场景下，继续追问：那在哪里配置？",
            "used_context": 1,
            "context_source": CONTEXT_SOURCE_REDIS,
            "user_id": f"{MARKER}_log",
            "group_id": f"{MARKER}_group",
            "source_type": MARKER,
            "should_write_log": True,
            "matched": 1,
            "confidence_level": "high",
            "answer_status": "hit",
            "answer": "请到系统设置中配置。",
        }
        log = AskLogService(session).create_question_log(state, latency_ms=100)
        log_id = log.id
        session.commit()

        saved = session.get(QuestionLog, log_id)
        if saved is None:
            _fail("question_log 上下文字段写入：记录不存在")
            return False
        if saved.used_context != 1 or saved.context_source != CONTEXT_SOURCE_REDIS:
            _fail("question_log 上下文字段写入：used_context/context_source 不正确")
            return False
        if saved.question_raw != "那在哪里配置？":
            _fail("question_log 上下文字段写入：question_raw 不正确")
            return False
        if not saved.rewritten_question or "合同系统" not in saved.rewritten_question:
            _fail("question_log 上下文字段写入：rewritten_question 不正确")
            return False
        print("[PASS] question_log 上下文字段写入通过")
        return True
    finally:
        if log_id is not None:
            session.execute(delete(QuestionLog).where(QuestionLog.id == log_id))
            session.commit()
        session.close()


def check_redis_degradation() -> bool:
    import asyncio

    async def _run() -> bool:
        session = SessionLocal()
        try:
            enhance_svc = ContextEnhanceService(
                session,
                conversation_service=ConversationContextService(store=BrokenConversationStore()),
            )
            result = await enhance_svc.enhance_question_async(
                question="那在哪里配置？",
                user_id=f"{MARKER}_degrade",
                group_id=f"{MARKER}_group",
            )
            # Redis 不可用时至少不能抛异常；可能无上下文增强或使用 30 天模块
            if result.original_question != "那在哪里配置？":
                _fail("Redis 异常降级：原始问题丢失")
                return False
            if result.context_source not in {CONTEXT_SOURCE_NONE, CONTEXT_SOURCE_MODULES}:
                _fail("Redis 异常降级：context_source 异常")
                return False
            print("[PASS] Redis 异常降级通过")
            return True
        finally:
            session.close()

    return asyncio.run(_run())


def check_list_user_recent_modules() -> bool:
    session = SessionLocal()
    suffix = uuid.uuid4().hex[:8]
    user_id = f"{MARKER}_repo_{suffix}"
    try:
        now = datetime.now()
        log = QuestionLog(
            request_id=f"{MARKER}-{uuid.uuid4().hex}",
            question_raw="测试",
            question_masked="测试",
            rewritten_question="测试",
            user_id=user_id,
            group_id=f"{MARKER}_group",
            source_type=MARKER,
            intent="question",
            matched=1,
            system_name="合同系统",
            module_name="审批流",
            create_time=now,
        )
        session.add(log)
        session.commit()

        rows = QuestionRepository(session).list_user_recent_modules(
            user_id=user_id,
            group_id=f"{MARKER}_group",
            days=30,
            limit=3,
        )
        if not rows:
            _fail("QuestionRepository.list_user_recent_modules：无结果")
            return False
        return True
    finally:
        session.execute(delete(QuestionLog).where(QuestionLog.user_id == user_id))
        session.commit()
        session.close()


def main() -> int:
    args = parse_args()
    apply_env_file(args.env_file)

    print("=" * 60)
    print("增强阶段6 多轮追问 + 30 天轻量记忆验收")
    print("=" * 60)

    checks = [
        check_imports,
        check_follow_up_rules,
        check_explicit_business_rules,
        check_redis_roundtrip,
        check_redis_rewrite,
        check_recent_modules_enhance,
        check_explicit_not_overwritten,
        check_question_log_fields,
        check_redis_degradation,
    ]

    for check in checks:
        if not check():
            print("-" * 60)
            print("[FAIL] 阶段6上下文增强验收未通过")
            return 1

    print("-" * 60)
    print("[PASS] 阶段6上下文增强验收通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
