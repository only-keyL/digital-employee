"""LLM provider selection and lazy client creation."""

from __future__ import annotations

from functools import lru_cache

from app.config.settings import settings
from app.llm.base import BaseLLMClient, LLMClientError
from app.llm.deepseek_client import DeepSeekClient
from app.llm.mock_llm import MockLLM


@lru_cache
def get_mock_llm() -> MockLLM:
    return MockLLM()


@lru_cache
def get_deepseek_client() -> DeepSeekClient:
    return DeepSeekClient()


class LLMFactory:
    @staticmethod
    def get_llm_client(*, force_mock: bool = False) -> BaseLLMClient:
        if force_mock or settings.is_mock_llm:
            if not force_mock and settings.llm_provider == "deepseek" and not settings.deepseek_api_key:
                print("[WARN] DEEPSEEK_API_KEY 为空，自动降级使用 MockLLM")
            return get_mock_llm()
        try:
            return get_deepseek_client()
        except LLMClientError as exc:
            print(f"[WARN] DeepSeekClient 初始化失败，自动降级 MockLLM: {exc}")
            return get_mock_llm()

    @staticmethod
    def use_deepseek_primary() -> bool:
        return settings.llm_provider == "deepseek" and bool(settings.deepseek_api_key)

    @staticmethod
    def get_primary_provider_name() -> str:
        client = LLMFactory.get_llm_client()
        return client.provider_name
