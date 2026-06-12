"""Local mock LLM for demo without API keys."""

from __future__ import annotations

import json
import re

from app.llm.base import BaseLLMClient, LLMResponse

MOCK_HEADER = "【当前为 Mock 模型回答】"
QUALITY_PASS_JSON = '{"pass": true, "risk_points": [], "suggestion": ""}'


class MockLLM(BaseLLMClient):
    """本地 Mock LLM：根据提示词模板生成演示用回答/质检/草稿 JSON。"""

    def __init__(self) -> None:
        self._model = "mock-llm"

    @property
    def provider_name(self) -> str:
        return "mock"

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_text = message.get("content", "")
                break

        if "待检查答案" in user_text or '"pass"' in user_text:
            content = QUALITY_PASS_JSON
        elif "知识卡片草稿" in user_text or '"title"' in user_text and "troubleshooting_steps" in user_text:
            content = self._build_knowledge_draft_json(user_text)
        else:
            content = self._build_answer(user_text)

        tokens = max(len(content) // 4, 0)
        return LLMResponse(
            content=content,
            tokens=tokens,
            provider=self.provider_name,
            model=self._model,
        )

    def _build_answer(self, prompt_text: str) -> str:
        question = self._extract_block(prompt_text, "用户问题：", "知识库内容：")
        context = self._extract_block(prompt_text, "知识库内容：", "请按以下格式回答")
        card = self._parse_first_card(context)

        system_name = card.get("system_name") or "未知系统"
        module_name = card.get("module_name") or "未知模块"
        title = card.get("title") or "知识卡片"
        card_id = card.get("card_id") or "未知"
        troubleshooting = card.get("troubleshooting_steps") or "暂无"
        solution = card.get("solution") or "暂无"
        risk_notice = card.get("risk_notice") or "涉及权限或生产环境操作前，建议人工确认后再处理。"

        question_hint = question.strip() or "当前实施问题"
        return (
            f"{MOCK_HEADER}\n"
            f"问题判断：根据知识库内容，该问题属于 {system_name} / {module_name} 相关问题，与“{question_hint}”相关。\n"
            f"排查步骤：\n{troubleshooting}\n\n"
            f"处理建议：\n{solution}\n\n"
            f"风险提醒：\n{risk_notice}\n\n"
            f"答案来源：{title}（card_id={card_id}）"
        )

    def _build_knowledge_draft_json(self, prompt_text: str) -> str:
        question = self._extract_block(prompt_text, "未命中问题：", "问题摘要：")
        summary = self._extract_block(prompt_text, "问题摘要：", "出现频次：")
        if not question:
            question = summary
        title = (summary or question)[:50] or "未命中问题知识卡片"
        return json.dumps(
            {
                "title": title,
                "question": question.strip() or summary.strip(),
                "answer": "【Mock 模型回答】待人工补充标准答案，请根据现场情况完善处理步骤。",
                "troubleshooting_steps": "1. 确认问题现象与复现条件；2. 检查相关配置与日志；3. 必要时联系二线支持。",
                "solution": "根据排查结果执行对应修复，并在测试环境验证后再推广。",
                "risk_notice": "涉及生产环境或权限变更前，建议人工确认后再处理。",
                "system_name": "待人工补充",
                "module_name": "待人工补充",
                "tags": "未命中沉淀,Mock草稿",
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _extract_block(text: str, start_marker: str, end_marker: str) -> str:
        start = text.find(start_marker)
        if start < 0:
            return ""
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end < 0:
            return text[start:].strip()
        return text[start:end].strip()

    @staticmethod
    def _parse_first_card(context: str) -> dict[str, str]:
        if not context.strip():
            return {}

        card_id_match = re.search(r"card_id=(\d+)", context)
        title_match = re.search(r"标题：(.+)", context)
        system_match = re.search(r"所属系统：(.+)", context)
        module_match = re.search(r"所属模块：(.+)", context)
        troubleshooting_match = re.search(r"排查步骤：([\s\S]*?)(?:\n解决方案：|\n风险提醒：|$)", context)
        solution_match = re.search(r"解决方案：([\s\S]*?)(?:\n风险提醒：|$)", context)
        risk_match = re.search(r"风险提醒：([\s\S]*?)(?:\n---|\Z)", context)

        return {
            "card_id": card_id_match.group(1) if card_id_match else "",
            "title": title_match.group(1).strip() if title_match else "",
            "system_name": system_match.group(1).strip() if system_match else "",
            "module_name": module_match.group(1).strip() if module_match else "",
            "troubleshooting_steps": troubleshooting_match.group(1).strip() if troubleshooting_match else "",
            "solution": solution_match.group(1).strip() if solution_match else "",
            "risk_notice": risk_match.group(1).strip() if risk_match else "",
        }
