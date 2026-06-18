"""Redis 沉淀会话服务：按 group_id + user_id 隔离，必须 TTL。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text
from app.infra.redis_client import RedisClient, RedisClientError
from app.schemas.wecom_message_schema import WeComMessage

logger = logging.getLogger(__name__)


class DepositSessionService:
    """管理指令式知识沉淀的 Redis session。"""

    def __init__(self, settings: Settings | None = None, redis_client: RedisClient | None = None) -> None:
        self.settings = settings or get_settings()
        self._redis = redis_client or RedisClient(self.settings)

    def build_session_key(self, message: WeComMessage) -> str:
        """生成 session key：deposit:session:{source}:{group|private}:{user_id}。"""
        group_part = message.group_id.strip() if message.group_id else f"private:{message.user_id}"
        return f"deposit:session:{message.source}:{group_part}:{message.user_id}"

    async def create_session(self, message: WeComMessage) -> dict:
        """创建沉淀 session 并设置 TTL。"""
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "source": message.source,
            "group_id": message.group_id,
            "user_id": message.user_id,
            "mode": "deposit",
            "started_at": now,
            "last_active_at": now,
        }
        key = self.build_session_key(message)
        ttl = self.settings.deposit_session_ttl_seconds
        try:
            await self._redis.set_value(key, json.dumps(payload, ensure_ascii=False), ttl_seconds=ttl)
            logger.info(
                "沉淀 session 已创建 key=%s user=%s ttl=%s",
                key,
                message.user_id,
                ttl,
            )
            return payload
        except RedisClientError as exc:
            logger.error("创建沉淀 session 失败：%s", exc)
            raise

    async def get_session(self, message: WeComMessage) -> dict | None:
        """查询沉淀 session。"""
        key = self.build_session_key(message)
        try:
            raw = await self._redis.get_value(key)
            if not raw:
                return None
            return json.loads(raw)
        except RedisClientError as exc:
            logger.error("查询沉淀 session 失败：%s", exc)
            raise
        except json.JSONDecodeError:
            logger.warning("沉淀 session JSON 损坏，key=%s", key)
            return None

    async def refresh_session(self, message: WeComMessage) -> None:
        """刷新 session TTL 与 last_active_at。"""
        session = await self.get_session(message)
        if session is None:
            return
        session["last_active_at"] = datetime.now(timezone.utc).isoformat()
        key = self.build_session_key(message)
        ttl = self.settings.deposit_session_ttl_seconds
        await self._redis.set_value(key, json.dumps(session, ensure_ascii=False), ttl_seconds=ttl)

    async def delete_session(self, message: WeComMessage) -> bool:
        """删除沉淀 session。"""
        key = self.build_session_key(message)
        try:
            deleted = await self._redis.delete_key(key)
            logger.info("沉淀 session 已删除 key=%s count=%s", key, deleted)
            return deleted > 0
        except RedisClientError as exc:
            logger.error("删除沉淀 session 失败：%s", exc)
            raise

    async def is_active(self, message: WeComMessage) -> bool:
        return (await self.get_session(message)) is not None

    def safe_log_content(self, content: str) -> str:
        """日志脱敏：不输出完整投稿正文。"""
        return sanitize_text(content, max_length=80)
