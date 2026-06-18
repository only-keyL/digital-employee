"""结构化知识卡片文本解析器。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

# 支持的字段标签（中文）
_FIELD_LABELS = (
    "标题",
    "问题",
    "答案",
    "系统",
    "模块",
    "标签",
    "场景",
    "原因分析",
    "排查步骤",
    "解决方案",
    "风险提示",
    "来源群",
    "来源人",
)

# 字段名到内部 key 的映射
_LABEL_TO_KEY = {
    "标题": "title",
    "问题": "question",
    "答案": "answer",
    "系统": "system_name",
    "模块": "module_name",
    "标签": "tags",
    "场景": "scene",
    "原因分析": "reason_analysis",
    "排查步骤": "troubleshooting_steps",
    "解决方案": "solution",
    "风险提示": "risk_notice",
    "来源群": "source_group",
    "来源人": "source_user",
}

_REQUIRED_KEYS = ("title", "question", "answer", "system_name", "module_name", "tags", "scene", "solution")
_REQUIRED_LABELS = ("标题", "问题", "答案", "系统", "模块", "标签", "场景", "解决方案")

_FIELD_HEADER_RE = re.compile(
    r"^(" + "|".join(re.escape(l) for l in _FIELD_LABELS) + r")[：:]\s*(.*)$"
)


@dataclass
class ParseResult:
    parsed_card: dict[str, str] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)


class KnowledgeCardParser:
    """从用户文本或 JSON 解析知识卡片字段。"""

    def parse(self, raw_content: str) -> ParseResult:
        text = (raw_content or "").strip()
        if not text:
            return ParseResult(missing_fields=list(_REQUIRED_LABELS))

        if text.startswith("{"):
            parsed = self._parse_json(text)
            if parsed is not None:
                return self._build_result(parsed)

        parsed = self._parse_labeled_text(text)
        return self._build_result(parsed)

    def _parse_json(self, text: str) -> dict[str, str] | None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        mapping = {
            "title": "title",
            "question": "question",
            "answer": "answer",
            "system_name": "system_name",
            "system": "system_name",
            "module_name": "module_name",
            "module": "module_name",
            "tags": "tags",
            "scene": "scene",
            "reason_analysis": "reason_analysis",
            "troubleshooting_steps": "troubleshooting_steps",
            "solution": "solution",
            "risk_notice": "risk_notice",
            "source_group": "source_group",
            "source_user": "source_user",
        }
        out: dict[str, str] = {}
        for src, dst in mapping.items():
            val = data.get(src)
            if val is not None and str(val).strip():
                out[dst] = str(val).strip()
        return out

    def _parse_labeled_text(self, text: str) -> dict[str, str]:
        """按「字段：值」分段解析，支持多行值。"""
        lines = text.splitlines()
        current_key: str | None = None
        buffer: list[str] = []
        parsed: dict[str, str] = {}

        def flush() -> None:
            nonlocal current_key, buffer
            if current_key and buffer:
                parsed[current_key] = "\n".join(buffer).strip()
            buffer = []

        for line in lines:
            m = _FIELD_HEADER_RE.match(line.strip())
            if m:
                flush()
                label, first_val = m.group(1), m.group(2)
                current_key = _LABEL_TO_KEY.get(label)
                buffer = [first_val] if first_val else []
            elif current_key:
                buffer.append(line.rstrip())

        flush()
        if "tags" in parsed:
            parsed["tags"] = self._normalize_tags(parsed["tags"])
        return parsed

    @staticmethod
    def _normalize_tags(tags: str) -> str:
        """标签支持逗号、顿号、空格分隔，统一为英文逗号。"""
        parts = re.split(r"[,，、\s]+", tags.strip())
        return ",".join(p for p in parts if p)

    def _build_result(self, parsed: dict[str, str]) -> ParseResult:
        missing: list[str] = []
        for key, label in zip(_REQUIRED_KEYS, _REQUIRED_LABELS, strict=True):
            if not (parsed.get(key) or "").strip():
                missing.append(label)
        return ParseResult(parsed_card=parsed, missing_fields=missing)
