"""Redis 异步客户端：懒连接，供基础设施健康检查使用。"""

from __future__ import annotations

import logging
from typing import Any

import redis.asyncio as aioredis

from app.config.settings import Settings
from app.core.desensitize import mask_url

logger = logging.getLogger(__name__)


class RedisClientError(Exception):
    """Redis 操作失败。"""


class RedisClient:
    """Redis 基础客户端：仅在调用方法时建立连接，不在模块导入时连接。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: aioredis.Redis | None = None

    def _ensure_configured(self) -> None:
        """校验 REDIS_URL 是否已配置。"""
        if not self._settings.redis_url.strip():
            raise RedisClientError("未配置 REDIS_URL，无法连接 Redis。")

    async def _get_client(self) -> aioredis.Redis:
        """懒创建 Redis 连接，避免 import 时立即连外部服务。"""
        self._ensure_configured()
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self._settings.redis_url,
                    decode_responses=True,
                )
            except Exception as exc:
                logger.error("Redis 连接初始化失败，URL=%s，原因=%s", mask_url(self._settings.redis_url), exc)
                raise RedisClientError(f"Redis 连接初始化失败：{exc}") from exc
        return self._client

    async def ping(self) -> bool:
        """Ping Redis，验证连通性。"""
        client = await self._get_client()
        try:
            result = await client.ping()
            return bool(result)
        except Exception as exc:
            logger.error("Redis ping 失败，URL=%s，原因=%s", mask_url(self._settings.redis_url), exc)
            raise RedisClientError(f"Redis ping 失败：{exc}") from exc

    async def set_value(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """写入键值，可选 TTL。"""
        client = await self._get_client()
        try:
            if ttl_seconds is not None:
                await client.set(key, value, ex=ttl_seconds)
            else:
                await client.set(key, value)
            return True
        except Exception as exc:
            logger.error("Redis set 失败，key=%s，原因=%s", key, exc)
            raise RedisClientError(f"Redis set 失败：{exc}") from exc

    async def get_value(self, key: str) -> str | None:
        """读取键值。"""
        client = await self._get_client()
        try:
            return await client.get(key)
        except Exception as exc:
            logger.error("Redis get 失败，key=%s，原因=%s", key, exc)
            raise RedisClientError(f"Redis get 失败：{exc}") from exc

    async def delete_key(self, key: str) -> int:
        """删除键，返回删除数量。"""
        client = await self._get_client()
        try:
            return int(await client.delete(key))
        except Exception as exc:
            logger.error("Redis delete 失败，key=%s，原因=%s", key, exc)
            raise RedisClientError(f"Redis delete 失败：{exc}") from exc

    async def close(self) -> None:
        """关闭 Redis 连接。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def safe_info(self) -> dict[str, Any]:
        """返回脱敏后的连接信息，供健康检查展示。"""
        return {
            "configured": bool(self._settings.redis_url.strip()),
            "redis_url": mask_url(self._settings.redis_url) if self._settings.redis_url else "",
        }
