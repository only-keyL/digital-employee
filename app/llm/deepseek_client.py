"""DeepSeek OpenAI-compatible client."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config.settings import settings
from app.llm.base import BaseLLMClient, LLMClientError, LLMResponse


class DeepSeekClient(BaseLLMClient):
    """DeepSeek OpenAI 兼容聊天客户端（基于 langchain-openai）。"""

    def __init__(self) -> None:
        if not settings.deepseek_api_key:
            raise LLMClientError("DEEPSEEK_API_KEY 未配置")
        self._model = settings.deepseek_model
        self._chat = ChatOpenAI(
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            model=self._model,
            timeout=settings.llm_timeout,
            max_tokens=settings.llm_max_tokens,
            temperature=0.2,
        )

    @property
    def provider_name(self) -> str:
        return "deepseek"

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        try:
            lc_messages = self._to_langchain_messages(messages)
            response = self._chat.invoke(lc_messages)
            if not isinstance(response, AIMessage):
                raise LLMClientError("DeepSeek 返回格式异常")
            content = str(response.content or "").strip()
            tokens = self._extract_tokens(response)
            return LLMResponse(
                content=content,
                tokens=tokens,
                provider=self.provider_name,
                model=self._model,
            )
        except LLMClientError:
            raise
        except Exception as exc:
            raise LLMClientError(str(exc)) from exc

    @staticmethod
    def _to_langchain_messages(messages: list[dict[str, str]]):
        converted = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                converted.append(SystemMessage(content=content))
            elif role == "assistant":
                converted.append(AIMessage(content=content))
            else:
                converted.append(HumanMessage(content=content))
        return converted

    @staticmethod
    def _extract_tokens(response: AIMessage) -> int:
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            response_metadata = getattr(response, "response_metadata", {}) or {}
            token_usage = response_metadata.get("token_usage") or {}
            total = token_usage.get("total_tokens")
            if total is not None:
                return int(total)
            return 0
        total = getattr(usage, "total_tokens", None)
        if total is not None:
            return int(total)
        return int(getattr(usage, "input_tokens", 0) or 0) + int(getattr(usage, "output_tokens", 0) or 0)
