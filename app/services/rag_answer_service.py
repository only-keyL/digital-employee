"""Stage3 RAG 答案生成服务：仅基于检索上下文调用 DeepSeek。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text
from app.infra.llm_client import LLMInfraClient, LLMInfraError
from app.rag.rag_retrieval_service import RagContextItem

logger = logging.getLogger(__name__)

_RAG_SYSTEM_PROMPT = """你是企业内部实施助手。
你只能基于【知识库上下文】回答。
如果上下文不足，请明确说“当前知识库没有足够依据”，不要编造。
回答要简洁、可执行。
涉及风险操作时必须提醒先备份、先测试、找负责人确认。"""

_LLM_DEGRADED_ANSWER = "当前模型服务暂时不可用，已记录问题，请稍后重试或联系管理员。"


@dataclass
class RagAnswerResult:
    answer: str
    status: str
    provider: str
    model: str
    prompt: str
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


class RagAnswerService:
    """组装 RAG prompt 并调用 DeepSeek 生成答案。"""

    def __init__(self, settings: Settings | None = None, llm_client: LLMInfraClient | None = None) -> None:
        self.settings = settings or get_settings()
        self.llm = llm_client or LLMInfraClient(self.settings)

    def build_prompt(self, question: str, contexts: list[RagContextItem]) -> str:
        blocks = []
        for idx, ctx in enumerate(contexts[:3], start=1):
            blocks.append(f"[知识{idx}]\n{ctx.content_text}")
        context_text = "\n\n".join(blocks)
        return (
            f"{_RAG_SYSTEM_PROMPT}\n\n"
            f"【知识库上下文】\n{context_text}\n\n"
            f"【用户问题】\n{question}\n\n"
            f"请基于上述上下文回答。"
        )

    async def generate(self, question: str, contexts: list[RagContextItem]) -> RagAnswerResult:
        prompt = self.build_prompt(question, contexts)
        started = time.perf_counter()
        try:
            answer = await self._chat(prompt)
            latency = int((time.perf_counter() - started) * 1000)
            logger.info(
                "RAG 答案生成成功 question=%s answer=%s",
                sanitize_text(question, max_length=80),
                sanitize_text(answer, max_length=80),
            )
            return RagAnswerResult(
                answer=answer,
                status="success",
                provider=self.settings.llm_provider,
                model=self.settings.llm_model,
                prompt=prompt,
                latency_ms=latency,
            )
        except LLMInfraError as exc:
            latency = int((time.perf_counter() - started) * 1000)
            logger.error("RAG 答案生成失败：%s", exc)
            return RagAnswerResult(
                answer=_LLM_DEGRADED_ANSWER,
                status="failed",
                provider=self.settings.llm_provider,
                model=self.settings.llm_model,
                prompt=prompt,
                latency_ms=latency,
                error_code="llm_failed",
                error_message=str(exc),
            )

    async def _chat(self, prompt: str) -> str:
        client = self.llm._get_client()
        response = await client.chat.completions.create(
            model=self.settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.settings.llm_temperature,
            max_tokens=min(1024, self.settings.llm_max_tokens),
        )
        return (response.choices[0].message.content or "").strip()
