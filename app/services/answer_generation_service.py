"""Generate answers with LLM after knowledge retrieval."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.llm.base import LLMClientError
from app.llm.llm_factory import LLMFactory
from app.llm.prompt_service import PromptService
from app.services.retrieval_service import RetrievalHit


@dataclass
class GeneratedAnswer:
    """AnswerGenerationService.generate 的返回结构。"""

    answer: str
    provider: str
    llm_tokens: int
    answer_time_ms: int
    need_human: bool
    risk_level: str
    fallback_reason: str | None
    error_stage: str | None
    error_message: str | None
    degraded: bool


class AnswerGenerationService:
    """命中后基于检索结果调用 LLM 生成答案。"""

    SOURCE_MARKER = "答案来源"

    def __init__(self, prompt_service: PromptService | None = None) -> None:
        self.prompt_service = prompt_service or PromptService()

    def generate(self, *, question: str, hits: list[RetrievalHit]) -> GeneratedAnswer:
        if not hits:
            raise ValueError("命中回答生成需要至少一条检索结果")

        context = self.build_context(hits)
        top_hit = hits[0]
        started = time.perf_counter()
        use_deepseek = LLMFactory.use_deepseek_primary()

        try:
            response = self.prompt_service.generate_answer(
                question=question,
                context=context,
                force_mock=not use_deepseek,
            )
            answer = self._ensure_source_line(response.content, top_hit)

            if use_deepseek:
                quality = self.prompt_service.check_quality(
                    question=question,
                    context=context,
                    answer=answer,
                    force_mock=False,
                )
                if not quality.passed:
                    return self._degrade_from_mock_or_template(
                        question=question,
                        context=context,
                        hits=hits,
                        started=started,
                        fallback_reason="答案质检未通过",
                        error_stage="llm_quality_check",
                        error_message=quality.suggestion or quality.raw_content[:500],
                    )

            elif not self._basic_format_valid(answer):
                return self._degrade_from_template(
                    hits=hits,
                    started=started,
                    fallback_reason="LLM降级回答",
                    error_stage="llm_format_check",
                    error_message="Mock 答案格式校验失败",
                )

            elapsed = int((time.perf_counter() - started) * 1000)
            return GeneratedAnswer(
                answer=answer,
                provider=response.provider,
                llm_tokens=response.tokens,
                answer_time_ms=elapsed,
                need_human=False,
                risk_level="low",
                fallback_reason=None,
                error_stage=None,
                error_message=None,
                degraded=False,
            )
        except LLMClientError as exc:
            if use_deepseek:
                return self._degrade_from_mock_or_template(
                    question=question,
                    context=context,
                    hits=hits,
                    started=started,
                    fallback_reason="LLM降级回答",
                    error_stage="llm_generate",
                    error_message=str(exc),
                )
            return self._degrade_from_template(
                hits=hits,
                started=started,
                fallback_reason="LLM降级回答",
                error_stage="llm_generate",
                error_message=str(exc),
            )
        except Exception as exc:
            return self._degrade_from_template(
                hits=hits,
                started=started,
                fallback_reason="LLM降级回答",
                error_stage="llm_generate",
                error_message=str(exc),
            )

    def build_context(self, hits: list[RetrievalHit]) -> str:
        """知识卡片在前，文档切片在后，作为 LLM 上下文。"""
        blocks: list[str] = []
        for hit in hits[:6]:
            if hit.source_type == "document_chunk" and hit.chunk is not None and hit.doc is not None:
                page = f"页码：{hit.page_no}" if hit.page_no else "页码：未知"
                blocks.append(
                    f"【文档切片 chunk_id={hit.chunk_id}】\n"
                    f"文档：《{hit.doc.doc_name}》\n"
                    f"章节：{hit.section_path or hit.chunk.section_title or '-'}\n"
                    f"{page}\n"
                    f"内容：\n{hit.chunk.content or ''}"
                )
                continue
            if hit.card is None:
                continue
            card = hit.card
            blocks.append(
                f"【知识卡片 card_id={card.id}】\n"
                f"标题：{card.title or ''}\n"
                f"标准问题：{card.question or ''}\n"
                f"标准答案：{card.answer or ''}\n"
                f"所属系统：{card.system_name or ''}\n"
                f"所属模块：{card.module_name or ''}\n"
                f"排查步骤：{card.troubleshooting_steps or ''}\n"
                f"解决方案：{card.solution or ''}\n"
                f"风险提醒：{card.risk_notice or ''}"
            )
        return "\n---\n".join(blocks)

    def _degrade_from_mock_or_template(
        self,
        *,
        question: str,
        context: str,
        hits: list[RetrievalHit],
        started: float,
        fallback_reason: str,
        error_stage: str,
        error_message: str,
    ) -> GeneratedAnswer:
        try:
            response = self.prompt_service.generate_answer(
                question=question,
                context=context,
                force_mock=True,
            )
            answer = self._ensure_source_line(response.content, hits[0])
            elapsed = int((time.perf_counter() - started) * 1000)
            return GeneratedAnswer(
                answer=answer,
                provider=response.provider,
                llm_tokens=response.tokens,
                answer_time_ms=elapsed,
                need_human=True,
                risk_level="medium",
                fallback_reason=fallback_reason,
                error_stage=error_stage,
                error_message=error_message,
                degraded=True,
            )
        except Exception as mock_exc:
            return self._degrade_from_template(
                hits=hits,
                started=started,
                fallback_reason=fallback_reason,
                error_stage=error_stage,
                error_message=f"{error_message}; mock_fallback={mock_exc}",
            )

    def _degrade_from_template(
        self,
        *,
        hits: list[RetrievalHit],
        started: float,
        fallback_reason: str,
        error_stage: str,
        error_message: str,
    ) -> GeneratedAnswer:
        elapsed = int((time.perf_counter() - started) * 1000)
        answer = self._build_template_answer(hits[0])
        return GeneratedAnswer(
            answer=answer,
            provider="template",
            llm_tokens=0,
            answer_time_ms=elapsed,
            need_human=True,
            risk_level="medium",
            fallback_reason=fallback_reason,
            error_stage=error_stage,
            error_message=error_message,
            degraded=True,
        )

    def _build_template_answer(self, hit: RetrievalHit) -> str:
        if hit.source_type == "document_chunk" and hit.chunk is not None and hit.doc is not None:
            page = f"第 {hit.page_no} 页" if hit.page_no else "未知页码"
            return (
                "【自动降级回答】\n"
                f"问题判断：根据文档《{hit.doc.doc_name}》相关内容作答。\n"
                f"章节：{hit.section_path or hit.chunk.section_title or '-'}\n"
                f"页码：{page}\n\n"
                f"内容摘要：\n{(hit.chunk.content or '')[:500]}\n\n"
                f"答案来源：{hit.doc.doc_name}（chunk_id={hit.chunk_id}）"
            )
        card = hit.card
        system_name = (card.system_name if card else None) or "未知系统"
        module_name = (card.module_name if card else None) or "未知模块"
        troubleshooting = (card.troubleshooting_steps if card else None) or "暂无"
        solution = (card.solution if card else None) or "暂无"
        risk_notice = (card.risk_notice if card else None) or "暂无"
        title = hit.title or (card.title if card else "未知")
        card_id = card.id if card else 0
        return (
            "【自动降级回答】\n"
            f"问题判断：根据当前知识卡片，该问题属于 {system_name} / {module_name} 相关问题。\n"
            f"排查步骤：\n{troubleshooting}\n\n"
            f"处理建议：\n{solution}\n\n"
            f"风险提醒：\n{risk_notice}\n\n"
            f"答案来源：{title}（card_id={card_id}）"
        )

    def _ensure_source_line(self, answer: str, hit: RetrievalHit) -> str:
        text = answer.strip()
        if self.SOURCE_MARKER in text:
            return text
        if hit.source_type == "document_chunk":
            doc_name = hit.doc_name or hit.title or "文档"
            return f"{text}\n\n答案来源：{doc_name}（chunk_id={hit.chunk_id}）"
        card_id = hit.card.id if hit.card else 0
        return f"{text}\n\n答案来源：{hit.title}（card_id={card_id}）"

    @staticmethod
    def _basic_format_valid(answer: str) -> bool:
        required = ["问题判断", "排查步骤", "处理建议", "风险提醒", "答案来源"]
        return all(marker in answer for marker in required)
