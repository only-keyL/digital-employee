"""Redis 会话上下文缓存服务：支持短期多轮追问。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Protocol

from app.config.settings import Settings, get_settings
from app.infra.redis_client import RedisClient, RedisClientError
from app.schemas.context_schema import ConversationContext

logger = logging.getLogger(__name__)

CONVERSATION_KEY_PREFIX = "digital_employee:conversation"
DEFAULT_TTL_SECONDS = 1800
MAX_ANSWER_SUMMARY_LENGTH = 300


class ConversationContextStore(Protocol):
    """会话上下文存储协议，便于验收脚本注入内存实现。"""

    async def get_value(self, key: str) -> str | None: ...

    async def set_value(self, key: str, value: str, ttl_seconds: int | None = None) -> bool: ...

    async def delete_key(self, key: str) -> int: ...


class ConversationContextService:
    """会话上下文缓存服务。

    使用 Redis 保存用户在某个群内最近一轮问答摘要，支持短期追问。
    Redis 异常时只降级为单轮问答，不影响主流程。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        redis_client: RedisClient | None = None,
        store: ConversationContextStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._redis = redis_client or RedisClient(self.settings)
        self._store = store

    @property
    def ttl_seconds(self) -> int:
        """短期上下文 TTL，默认 30 分钟。"""
        return getattr(self.settings, "conversation_context_ttl_seconds", DEFAULT_TTL_SECONDS)

    def build_context_key(self, *, user_id: str, group_id: str | None) -> str:
        """生成 Redis key：群维度优先，私聊使用 private 前缀。"""
        safe_user = (user_id or "anonymous").strip()
        if group_id and group_id.strip():
            return f"{CONVERSATION_KEY_PREFIX}:{group_id.strip()}:{safe_user}"
        return f"{CONVERSATION_KEY_PREFIX}:private:{safe_user}"

    async def get_recent_context(self, *, user_id: str, group_id: str | None) -> ConversationContext | None:
        """读取用户最近一轮问答上下文，Redis 失败时返回 None。"""
        key = self.build_context_key(user_id=user_id, group_id=group_id)
        try:
            raw = await self._get_store().get_value(key)
            if not raw:
                return None
            data = json.loads(raw)
            return ConversationContext.model_validate(data)
        except RedisClientError as exc:
            logger.warning("读取会话上下文失败，降级为单轮问答 key=%s 原因=%s", key, exc)
            return None
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("会话上下文 JSON 损坏 key=%s 原因=%s", key, exc)
            return None

    async def save_recent_context(
        self,
        *,
        user_id: str,
        group_id: str | None,
        question: str,
        rewritten_question: str | None,
        answer: str | None,
        system_name: str | None,
        module_name: str | None,
        primary_matched_card_id: int | None,
        primary_matched_card_title: str | None,
        confidence_level: str | None,
    ) -> None:
        """保存用户最近一轮问答上下文，写入失败不中断主流程。"""
        if not (user_id or "").strip():
            return
        if not (answer or "").strip():
            return

        payload = ConversationContext(
            last_question=(question or "").strip(),
            last_rewritten_question=(rewritten_question or question or "").strip() or None,
            last_answer_summary=self._summarize_answer(answer),
            system_name=system_name,
            module_name=module_name,
            primary_matched_card_id=primary_matched_card_id,
            primary_matched_card_title=primary_matched_card_title,
            confidence_level=confidence_level,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        key = self.build_context_key(user_id=user_id, group_id=group_id)
        try:
            await self._get_store().set_value(
                key,
                payload.model_dump_json(),
                ttl_seconds=self.ttl_seconds,
            )
            logger.info("会话上下文已保存 key=%s ttl=%s", key, self.ttl_seconds)
        except RedisClientError as exc:
            logger.warning("保存会话上下文失败，不影响问答主流程 key=%s 原因=%s", key, exc)

    async def clear_context(self, *, user_id: str, group_id: str | None) -> None:
        """清除用户短期上下文。"""
        key = self.build_context_key(user_id=user_id, group_id=group_id)
        try:
            await self._get_store().delete_key(key)
        except RedisClientError as exc:
            logger.warning("清除会话上下文失败 key=%s 原因=%s", key, exc)

    def get_recent_context_sync(self, *, user_id: str, group_id: str | None) -> ConversationContext | None:
        """同步读取上下文，供 /api/ask 同步链路使用。"""
        return asyncio.run(self.get_recent_context(user_id=user_id, group_id=group_id))

    def save_recent_context_sync(self, **kwargs) -> None:
        """同步保存上下文，供 /api/ask 同步链路使用。"""
        asyncio.run(self.save_recent_context(**kwargs))

    def _get_store(self) -> ConversationContextStore:
        return self._store or self._redis

    @staticmethod
    def _summarize_answer(answer: str | None) -> str | None:
        """截断回答摘要，避免 Redis 存储过长内容。"""
        text = (answer or "").strip()
        if not text:
            return None
        if len(text) <= MAX_ANSWER_SUMMARY_LENGTH:
            return text
        return text[:MAX_ANSWER_SUMMARY_LENGTH]
