"""DeepSeek LLM 基础设施客户端：最小真实调用，不接入问答主链路。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config.settings import Settings
from app.core.desensitize import sanitize_text

logger = logging.getLogger(__name__)

_INFRA_PROBE_PROMPT = "请只回复 pong"


class LLMInfraError(Exception):
    """LLM 基础设施调用失败。"""


class LLMInfraClient:
    """DeepSeek 基础设施客户端：仅用于连通性探测。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncOpenAI | None = None

    def _ensure_real_provider(self) -> None:
        """mock 模式不允许作为阶段 2 DeepSeek 验收通过。"""
        if self._settings.llm_provider.lower() == "mock":
            raise LLMInfraError("LLM_PROVIDER=mock，跳过真实 DeepSeek 调用。")
        if not self._settings.llm_api_key.strip():
            raise LLMInfraError("未配置 LLM_API_KEY，无法调用 DeepSeek。")

    def _get_client(self) -> AsyncOpenAI:
        """懒创建 OpenAI 兼容客户端。"""
        self._ensure_real_provider()
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self._settings.llm_api_key,
                base_url=self._settings.llm_base_url or None,
                timeout=float(self._settings.llm_timeout),
                max_retries=self._settings.llm_max_retries,
            )
        return self._client

    async def simple_chat(self, prompt: str = _INFRA_PROBE_PROMPT) -> str:
        """发起一次最小 chat 调用，验证 DeepSeek 连通性。"""
        client = self._get_client()
        safe_prompt = sanitize_text(prompt, max_length=50)
        last_error: Exception | None = None

        for attempt in range(1, self._settings.llm_max_retries + 2):
            try:
                response = await client.chat.completions.create(
                    model=self._settings.llm_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._settings.llm_temperature,
                    max_tokens=16,
                )
                content = (response.choices[0].message.content or "").strip()
                logger.info("DeepSeek 基础设施探测成功，prompt=%s，response=%s", safe_prompt, sanitize_text(content))
                return content
            except Exception as exc:
                last_error = exc
                logger.warning("DeepSeek 调用失败（第 %d 次），原因=%s", attempt, exc)
                if attempt <= self._settings.llm_max_retries:
                    await asyncio.sleep(0.5 * attempt)

        raise LLMInfraError(f"DeepSeek 调用失败：{last_error}") from last_error

    def safe_info(self) -> dict[str, Any]:
        """返回脱敏后的 LLM 配置信息。"""
        return {
            "configured": bool(self._settings.llm_api_key.strip()),
            "provider": self._settings.llm_provider,
            "model": self._settings.llm_model,
            "is_mock": self._settings.is_mock_llm,
        }
