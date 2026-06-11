"""Shared LLM client types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    tokens: int
    provider: str
    model: str


class BaseLLMClient(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        raise NotImplementedError


class LLMClientError(Exception):
    pass
