"""文档切片：按段落/章节合并为 500～1000 字 chunk。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.services.document_parse_service import ParseSegment

MIN_CHUNK_CHARS = 500
MAX_CHUNK_CHARS = 1000
STEP_LINE_RE = re.compile(r"^(\d+[\.、\)]|[一二三四五六七八九十]+[、\.]|步骤\s*\d+)", re.MULTILINE)


@dataclass
class ChunkDraft:
    """待入库的切片草稿。"""

    chunk_index: int
    section_title: str | None
    section_path: str | None
    page_no: int | None
    content: str
    content_hash: str
    token_estimate: int


class DocumentChunkService:
    """文档切片服务：合并短段、拆分长段，并附加来源上下文。"""

    def build_chunks(
        self,
        segments: list[ParseSegment],
        *,
        doc_name: str,
        system_name: str | None,
        module_name: str | None,
    ) -> list[ChunkDraft]:
        merged_blocks = self._merge_segments(segments)
        chunks: list[ChunkDraft] = []
        for index, block in enumerate(merged_blocks, start=1):
            body = block.text.strip()
            if not body:
                continue
            prefixed = self._build_context_prefix(
                doc_name=doc_name,
                system_name=system_name,
                module_name=module_name,
                section_path=block.section_path,
                body=body,
            )
            chunks.append(
                ChunkDraft(
                    chunk_index=index,
                    section_title=block.section_title or None,
                    section_path=block.section_path or None,
                    page_no=block.page_no,
                    content=prefixed,
                    content_hash=hashlib.sha256(prefixed.encode("utf-8")).hexdigest(),
                    token_estimate=len(prefixed),
                )
            )
        return chunks

    def _merge_segments(self, segments: list[ParseSegment]) -> list[ParseSegment]:
        """将解析片段合并/拆分为目标长度块，尽量不打散步骤列表。"""
        blocks: list[ParseSegment] = []
        buffer_text = ""
        buffer_meta = ParseSegment(text="", section_title="", section_path="", page_no=None)

        def flush() -> None:
            nonlocal buffer_text, buffer_meta
            text = buffer_text.strip()
            if text:
                blocks.append(
                    ParseSegment(
                        text=text,
                        section_title=buffer_meta.section_title,
                        section_path=buffer_meta.section_path,
                        page_no=buffer_meta.page_no,
                    )
                )
            buffer_text = ""

        for segment in segments:
            parts = self._split_long_segment(segment)
            for part in parts:
                part_len = len(part.text)
                if not buffer_text:
                    buffer_meta = part
                    buffer_text = part.text
                    continue

                if self._contains_step_lines(part.text) or self._contains_step_lines(buffer_text):
                    if len(buffer_text) + part_len + 2 <= MAX_CHUNK_CHARS:
                        buffer_text = f"{buffer_text}\n\n{part.text}"
                    else:
                        flush()
                        buffer_meta = part
                        buffer_text = part.text
                    continue

                if len(buffer_text) + part_len + 2 <= MAX_CHUNK_CHARS:
                    buffer_text = f"{buffer_text}\n\n{part.text}"
                else:
                    if len(buffer_text) < MIN_CHUNK_CHARS and len(buffer_text) + part_len + 2 <= MAX_CHUNK_CHARS * 1.2:
                        buffer_text = f"{buffer_text}\n\n{part.text}"
                    else:
                        flush()
                        buffer_meta = part
                        buffer_text = part.text

        flush()
        return blocks

    def _split_long_segment(self, segment: ParseSegment) -> list[ParseSegment]:
        text = segment.text.strip()
        if len(text) <= MAX_CHUNK_CHARS:
            return [segment]
        if self._contains_step_lines(text):
            lines = text.splitlines()
            parts: list[str] = []
            current: list[str] = []
            for line in lines:
                current.append(line)
                if len("\n".join(current)) >= MAX_CHUNK_CHARS:
                    parts.append("\n".join(current).strip())
                    current = []
            if current:
                parts.append("\n".join(current).strip())
        else:
            parts = [
                text[i : i + MAX_CHUNK_CHARS].strip()
                for i in range(0, len(text), MAX_CHUNK_CHARS)
                if text[i : i + MAX_CHUNK_CHARS].strip()
            ]
        return [
            ParseSegment(
                text=part,
                section_title=segment.section_title,
                section_path=segment.section_path,
                page_no=segment.page_no,
            )
            for part in parts
        ]

    @staticmethod
    def _contains_step_lines(text: str) -> bool:
        return bool(STEP_LINE_RE.search(text))

    @staticmethod
    def _build_context_prefix(
        *,
        doc_name: str,
        system_name: str | None,
        module_name: str | None,
        section_path: str,
        body: str,
    ) -> str:
        lines = [f"文档：《{doc_name}》"]
        if system_name:
            lines.append(f"系统：{system_name}")
        if module_name:
            lines.append(f"模块：{module_name}")
        if section_path:
            lines.append(f"章节：{section_path}")
        lines.extend(["", "正文：", body])
        return "\n".join(lines)
