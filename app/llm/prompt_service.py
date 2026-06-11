"""Prompt rendering and LLM invocation."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from app.llm.base import LLMClientError, LLMResponse
from app.llm.llm_factory import LLMFactory
from app.prompts.answer_prompt import ANSWER_PROMPT_TEMPLATE
from app.prompts.knowledge_draft_prompt import KNOWLEDGE_DRAFT_PROMPT_TEMPLATE
from app.prompts.quality_check_prompt import QUALITY_CHECK_PROMPT_TEMPLATE


@dataclass
class QualityCheckResult:
    passed: bool
    risk_points: list[str]
    suggestion: str
    raw_content: str


class PromptService:
    def render_answer_prompt(self, *, question: str, context: str) -> str:
        return (
            ANSWER_PROMPT_TEMPLATE.replace("{{question}}", question.strip())
            .replace("{{context}}", context.strip())
        )

    def render_quality_prompt(self, *, question: str, context: str, answer: str) -> str:
        return (
            QUALITY_CHECK_PROMPT_TEMPLATE.replace("{{question}}", question.strip())
            .replace("{{context}}", context.strip())
            .replace("{{answer}}", answer.strip())
        )

    def render_knowledge_draft_prompt(
        self,
        *,
        question: str,
        summary: str,
        frequency: int,
        system_name: str = "",
        module_name: str = "",
        tags: str = "",
    ) -> str:
        return (
            KNOWLEDGE_DRAFT_PROMPT_TEMPLATE.replace("{{question}}", question.strip())
            .replace("{{summary}}", summary.strip())
            .replace("{{frequency}}", str(frequency))
            .replace("{{system_name}}", system_name.strip() or "无")
            .replace("{{module_name}}", module_name.strip() or "无")
            .replace("{{tags}}", tags.strip() or "无")
        )

    def generate_knowledge_draft(
        self,
        *,
        question: str,
        summary: str,
        frequency: int,
        system_name: str = "",
        module_name: str = "",
        tags: str = "",
        force_mock: bool = False,
    ) -> LLMResponse:
        prompt = self.render_knowledge_draft_prompt(
            question=question,
            summary=summary,
            frequency=frequency,
            system_name=system_name,
            module_name=module_name,
            tags=tags,
        )
        messages = [
            {"role": "system", "content": "你是企业内部知识库编辑助手。"},
            {"role": "user", "content": prompt},
        ]
        client = LLMFactory.get_llm_client(force_mock=force_mock)
        try:
            response = client.chat(messages)
        except LLMClientError:
            raise
        except Exception as exc:
            raise LLMClientError(str(exc)) from exc
        return response

    def generate_answer(
        self,
        *,
        question: str,
        context: str,
        force_mock: bool = False,
    ) -> LLMResponse:
        prompt = self.render_answer_prompt(question=question, context=context)
        messages = [
            {"role": "system", "content": "你是企业内部实施问题数字员工。"},
            {"role": "user", "content": prompt},
        ]
        client = LLMFactory.get_llm_client(force_mock=force_mock)
        started = time.perf_counter()
        try:
            response = client.chat(messages)
        except LLMClientError:
            raise
        except Exception as exc:
            raise LLMClientError(str(exc)) from exc
        _ = started
        return response

    def check_quality(
        self,
        *,
        question: str,
        context: str,
        answer: str,
        force_mock: bool = False,
    ) -> QualityCheckResult:
        prompt = self.render_quality_prompt(question=question, context=context, answer=answer)
        messages = [
            {"role": "system", "content": "你是企业 AI 答案质检助手。"},
            {"role": "user", "content": prompt},
        ]
        client = LLMFactory.get_llm_client(force_mock=force_mock)
        try:
            response = client.chat(messages)
        except LLMClientError:
            raise
        except Exception as exc:
            raise LLMClientError(str(exc)) from exc
        return self._parse_quality_result(response.content)

    @staticmethod
    def _parse_quality_result(raw_content: str) -> QualityCheckResult:
        text = raw_content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            payload = json.loads(text)
            return QualityCheckResult(
                passed=bool(payload.get("pass")),
                risk_points=list(payload.get("risk_points") or []),
                suggestion=str(payload.get("suggestion") or ""),
                raw_content=raw_content,
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return QualityCheckResult(
                passed=False,
                risk_points=[],
                suggestion="质检 JSON 解析失败",
                raw_content=raw_content,
            )
