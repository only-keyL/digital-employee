"""基础设施健康检查 Service：汇总 Redis / Qdrant / LLM / LangSmith 状态。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.config.settings import Settings
from app.core.desensitize import sanitize_dict
from app.infra.langsmith_tracing import LangSmithInfraError, run_langsmith_probe
from app.infra.llm_client import LLMInfraClient, LLMInfraError
from app.infra.qdrant_client import QdrantInfraClient, QdrantInfraError
from app.infra.redis_client import RedisClient, RedisClientError

logger = logging.getLogger(__name__)

_REDIS_PROBE_KEY = "dea:stage2:infra:probe"


class InfraHealthService:
    """基础设施健康检查：支持 shallow（仅配置）与 deep（真实调用）两种模式。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def check_redis(self, *, deep: bool = False) -> dict[str, Any]:
        """检查 Redis 配置或连通性。"""
        client = RedisClient(self._settings)
        base = {"name": "redis", **client.safe_info()}

        if not self._settings.redis_url.strip():
            return {**base, "status": "failed", "message": "未配置 REDIS_URL。"}

        if not deep:
            return {**base, "status": "configured", "message": "Redis 已配置。"}

        try:
            ping_ok = await client.ping()
            probe_value = "stage2_ok"
            await client.set_value(_REDIS_PROBE_KEY, probe_value, ttl_seconds=60)
            got = await client.get_value(_REDIS_PROBE_KEY)
            await client.delete_key(_REDIS_PROBE_KEY)
            await client.close()
            if not ping_ok or got != probe_value:
                return {**base, "status": "failed", "message": "Redis ping 或 set/get 验证失败。"}
            return {**base, "status": "ok", "message": "Redis ping / set / get 成功。"}
        except RedisClientError as exc:
            await client.close()
            return {**base, "status": "failed", "message": str(exc)}

    async def check_qdrant(self, *, deep: bool = False, allow_write: bool = False) -> dict[str, Any]:
        """检查 Qdrant 配置或连通性；写入测试向量需 allow_write=True。"""
        client = QdrantInfraClient(self._settings)
        base = {"name": "qdrant", **client.safe_info()}

        if self._settings.qdrant_mode.lower() != "remote":
            return {
                **base,
                "status": "skipped" if not deep else "failed",
                "message": f"当前 QDRANT_MODE={self._settings.qdrant_mode}，远程检查需 remote。",
            }
        if not self._settings.qdrant_url.strip():
            return {**base, "status": "failed", "message": "未配置 QDRANT_URL。"}

        if not deep:
            return {**base, "status": "configured", "message": "Qdrant 远程配置已就绪。"}

        try:
            client.check_connection()
            result: dict[str, Any] = {**base, "status": "ok", "message": "Qdrant 远程连接成功。"}

            if allow_write:
                point_id = client.upsert_test_point(allow_write=True)
                hits = client.search_test_point()
                result["write_probe"] = "ok"
                result["point_id"] = point_id
                result["search_hits"] = len(hits)
                result["message"] = "Qdrant 连接、写入测试向量、检索均成功。"
            else:
                result["write_probe"] = "skipped"
                result["message"] = "Qdrant 连接成功（未写入测试向量）。"
            return result
        except QdrantInfraError as exc:
            return {**base, "status": "failed", "message": str(exc)}

    async def check_llm(self, *, deep: bool = False) -> dict[str, Any]:
        """检查 LLM 配置或 DeepSeek 最小调用。"""
        client = LLMInfraClient(self._settings)
        base = {"name": "llm", **client.safe_info()}

        if self._settings.llm_provider.lower() == "mock":
            return {**base, "status": "skipped", "message": "LLM_PROVIDER=mock，跳过真实 DeepSeek 调用。"}
        if not self._settings.llm_api_key.strip():
            return {**base, "status": "failed", "message": "未配置 LLM_API_KEY。"}

        if not deep:
            return {**base, "status": "configured", "message": "DeepSeek 配置已就绪。"}

        try:
            content = await client.simple_chat()
            return {
                **base,
                "status": "ok",
                "message": "DeepSeek 最小调用成功。",
                "response_preview": content[:20],
            }
        except LLMInfraError as exc:
            return {**base, "status": "failed", "message": str(exc)}

    async def check_langsmith(self, *, deep: bool = False) -> dict[str, Any]:
        """检查 LangSmith 配置或测试 trace。"""
        base = {
            "name": "langsmith",
            "tracing": self._settings.langsmith_tracing,
            "project": self._settings.langsmith_project,
            "configured": bool(self._settings.langsmith_api_key.strip()),
        }

        if not self._settings.langsmith_tracing:
            return {**base, "status": "disabled", "message": "LANGSMITH_TRACING=false。"}

        if not self._settings.langsmith_api_key.strip():
            return {**base, "status": "skipped", "message": "未配置 LANGSMITH_API_KEY。"}

        if not deep:
            return {**base, "status": "configured", "message": "LangSmith 已配置。"}

        try:
            probe_result = await asyncio.to_thread(run_langsmith_probe, self._settings)
            return {**base, **probe_result}
        except LangSmithInfraError as exc:
            return {**base, "status": "failed", "message": str(exc)}

    async def check_all(
        self,
        *,
        deep: bool = False,
        allow_qdrant_write: bool = False,
    ) -> dict[str, Any]:
        """汇总全部基础设施检查结果，单项失败不影响其他项返回。"""
        checks = {
            "redis": await self.check_redis(deep=deep),
            "qdrant": await self.check_qdrant(deep=deep, allow_write=allow_qdrant_write),
            "llm": await self.check_llm(deep=deep),
            "langsmith": await self.check_langsmith(deep=deep),
        }

        failed = [name for name, item in checks.items() if item.get("status") == "failed"]
        skipped = [name for name, item in checks.items() if item.get("status") in {"skipped", "disabled"}]

        if failed:
            overall = "degraded"
        elif skipped and len(skipped) == len(checks):
            overall = "skipped"
        else:
            overall = "ok"

        payload = {
            "status": overall,
            "env": self._settings.app_env,
            "deep": deep,
            "checks": checks,
        }
        return sanitize_dict(payload)
