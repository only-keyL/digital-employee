"""共享 LLM 客户端类型定义。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """LLM 单次 chat 调用的统一返回结构。"""

    content: str  # 模型输出文本
    tokens: int  # token 消耗（估算或实际）
    provider: str  # 提供方：mock / deepseek 等
    model: str  # 模型名称


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类。"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供方名称。"""
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        """发送 chat messages 并返回 LLMResponse。"""
        raise NotImplementedError


class LLMClientError(Exception):
    """LLM 调用失败异常。"""

    pass
