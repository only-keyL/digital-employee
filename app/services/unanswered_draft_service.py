"""AI/Mock assisted knowledge card draft preview from unanswered questions."""

from __future__ import annotations

import json
import re

from app.llm.base import LLMClientError
from app.llm.llm_factory import LLMFactory
from app.llm.prompt_service import PromptService
from app.models.unanswered_question import UnansweredQuestion
from app.prompts.knowledge_draft_prompt import KNOWLEDGE_DRAFT_PROMPT_TEMPLATE
from app.schemas.unanswered_schema import UnansweredDraftPreview


class UnansweredDraftService:
    """未命中问题 AI/Mock 知识卡片草稿预览生成。"""

    def __init__(self, prompt_service: PromptService | None = None) -> None:
        self.prompt_service = prompt_service or PromptService()

    def generate_preview(self, record: UnansweredQuestion) -> UnansweredDraftPreview:
        question = (record.question or "").strip()
        summary = (record.summary or question[:100]).strip()
        use_deepseek = LLMFactory.use_deepseek_primary()

        try:
            response = self.prompt_service.generate_knowledge_draft(
                question=question,
                summary=summary,
                frequency=record.frequency,
                system_name=record.system_name or "",
                module_name=record.module_name or "",
                tags=record.tags or "",
                force_mock=not use_deepseek,
            )
            parsed = self._parse_draft_json(response.content)
            if parsed:
                return UnansweredDraftPreview(
                    **parsed,
                    provider=response.provider,
                    degraded=False,
                )
            if use_deepseek:
                return self._mock_or_template(record, summary, degraded=True, reason="json_parse")
        except LLMClientError:
            if use_deepseek:
                return self._mock_or_template(record, summary, degraded=True, reason="llm_error")
            return self._template_fallback(record, summary, degraded=True)

        return self._mock_or_template(record, summary, degraded=not use_deepseek, reason="format")

    def _mock_or_template(
        self,
        record: UnansweredQuestion,
        summary: str,
        *,
        degraded: bool,
        reason: str,
    ) -> UnansweredDraftPreview:
        try:
            response = self.prompt_service.generate_knowledge_draft(
                question=(record.question or "").strip(),
                summary=summary,
                frequency=record.frequency,
                system_name=record.system_name or "",
                module_name=record.module_name or "",
                tags=record.tags or "",
                force_mock=True,
            )
            parsed = self._parse_draft_json(response.content)
            if parsed:
                return UnansweredDraftPreview(
                    **parsed,
                    provider=response.provider,
                    degraded=degraded,
                )
        except Exception:
            pass
        return self._template_fallback(record, summary, degraded=True)

    def _template_fallback(
        self,
        record: UnansweredQuestion,
        summary: str,
        *,
        degraded: bool,
    ) -> UnansweredDraftPreview:
        question = (record.question or summary).strip()
        title = summary[:50] or question[:50] or "未命中问题沉淀"
        return UnansweredDraftPreview(
            title=title,
            question=question,
            answer="待人工补充标准答案",
            troubleshooting_steps="待人工补充排查步骤",
            solution="待人工补充处理建议",
            risk_notice="涉及生产环境或权限变更前，建议人工确认后再处理。",
            system_name=(record.system_name or "").strip(),
            module_name=(record.module_name or "").strip(),
            tags=(record.tags or "").strip(),
            provider="template",
            degraded=degraded,
        )

    @staticmethod
    def _parse_draft_json(raw_content: str) -> dict[str, str] | None:
        text = raw_content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        title = str(payload.get("title") or "").strip()
        question = str(payload.get("question") or "").strip()
        answer = str(payload.get("answer") or "").strip()
        if not title or not question or not answer:
            return None

        return {
            "title": title[:200],
            "question": question,
            "answer": answer,
            "troubleshooting_steps": str(payload.get("troubleshooting_steps") or "").strip(),
            "solution": str(payload.get("solution") or "").strip(),
            "risk_notice": str(payload.get("risk_notice") or "").strip(),
            "system_name": str(payload.get("system_name") or "").strip(),
            "module_name": str(payload.get("module_name") or "").strip(),
            "tags": str(payload.get("tags") or "").strip(),
        }
