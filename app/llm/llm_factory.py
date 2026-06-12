"""LLM Provider 选择与懒加载客户端。"""

from __future__ import annotations

from functools import lru_cache

from app.config.settings import settings
from app.llm.base import BaseLLMClient, LLMClientError
from app.llm.deepseek_client import DeepSeekClient
from app.llm.mock_llm import MockLLM


@lru_cache
def get_mock_llm() -> MockLLM:
    """获取进程内 MockLLM 单例。"""
    return MockLLM()


@lru_cache
def get_deepseek_client() -> DeepSeekClient:
    """获取进程内 DeepSeekClient 单例。"""
    return DeepSeekClient()


class LLMFactory:
    """根据 settings 选择 Mock 或 DeepSeek，支持 force_mock 降级。"""

    @staticmethod
    def get_llm_client(*, force_mock: bool = False) -> BaseLLMClient:
        """返回可用的 LLM 客户端；无 Key 或失败时降级 MockLLM。"""
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
        """当前是否以 DeepSeek 为主 Provider（有 Key 且 llm_provider=deepseek）。"""
        return settings.llm_provider == "deepseek" and bool(settings.deepseek_api_key)

    @staticmethod
    def get_primary_provider_name() -> str:
        """返回当前主 Provider 名称字符串。"""
        client = LLMFactory.get_llm_client()
        return client.provider_name
