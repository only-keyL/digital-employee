"""文档文本解析：txt / md / docx / pdf 基础提取。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParseSegment:
    """解析后的文本片段，供切片服务合并。"""

    text: str
    section_title: str = ""
    section_path: str = ""
    page_no: int | None = None


class DocumentParseError(Exception):
    """文档解析失败。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DocumentParseService:
    """文档解析入口：按扩展名路由到对应解析器。"""

    MARKDOWN_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$")

    def parse_file(self, file_path: str | Path, file_ext: str) -> list[ParseSegment]:
        path = Path(file_path)
        ext = file_ext.lower().lstrip(".")
        if ext == "txt":
            return self._parse_txt(path.read_text(encoding="utf-8", errors="replace"))
        if ext == "md":
            return self._parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
        if ext == "docx":
            return self._parse_docx(path)
        if ext == "pdf":
            return self._parse_pdf(path)
        raise DocumentParseError(f"不支持的文件类型: .{ext}")

    def parse_text(self, text: str, file_ext: str) -> list[ParseSegment]:
        """解析内存文本（验收脚本与单元测试使用）。"""
        ext = file_ext.lower().lstrip(".")
        if ext == "md":
            return self._parse_markdown(text)
        if ext == "txt":
            return self._parse_txt(text)
        raise DocumentParseError(f"parse_text 不支持: .{ext}")

    def _parse_txt(self, text: str) -> list[ParseSegment]:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        if not paragraphs:
            raise DocumentParseError("TXT 文件未提取到有效文本")
        return [ParseSegment(text=p, section_title="", section_path="") for p in paragraphs]

    def _parse_markdown(self, text: str) -> list[ParseSegment]:
        """Markdown 标题切片：优先按 # / ## / ### 识别章节。"""
        lines = text.splitlines()
        segments: list[ParseSegment] = []
        path_stack: list[tuple[int, str]] = []
        current_title = ""
        current_path = ""
        buffer: list[str] = []

        def flush_buffer() -> None:
            nonlocal buffer, current_title, current_path
            body = "\n".join(buffer).strip()
            if body:
                segments.append(
                    ParseSegment(
                        text=body,
                        section_title=current_title,
                        section_path=current_path,
                    )
                )
            buffer = []

        for line in lines:
            match = self.MARKDOWN_HEADER_RE.match(line.strip())
            if match:
                flush_buffer()
                level = len(match.group(1))
                title = match.group(2).strip()
                while path_stack and path_stack[-1][0] >= level:
                    path_stack.pop()
                path_stack.append((level, title))
                current_title = title
                current_path = " / ".join(item[1] for item in path_stack)
            else:
                buffer.append(line)

        flush_buffer()
        if not segments:
            raise DocumentParseError("Markdown 文件未提取到有效文本")
        return segments

    def _parse_docx(self, path: Path) -> list[ParseSegment]:
        try:
            from docx import Document
        except ImportError as exc:
            raise DocumentParseError("缺少 python-docx 依赖，无法解析 docx") from exc

        doc = Document(str(path))
        segments: list[ParseSegment] = []
        path_stack: list[tuple[int, str]] = []
        current_title = ""
        current_path = ""
        buffer: list[str] = []

        def flush_buffer() -> None:
            nonlocal buffer, current_title, current_path
            body = "\n".join(buffer).strip()
            if body:
                segments.append(
                    ParseSegment(
                        text=body,
                        section_title=current_title,
                        section_path=current_path,
                    )
                )
            buffer = []

        for para in doc.paragraphs:
            text = (para.text or "").strip()
            if not text:
                continue
            style_name = para.style.name if para.style is not None else ""
            is_heading = style_name.startswith("Heading") or "标题" in style_name
            if is_heading:
                flush_buffer()
                level = 1
                if style_name.startswith("Heading"):
                    try:
                        level = int(style_name.replace("Heading", "").strip() or "1")
                    except ValueError:
                        level = 1
                while path_stack and path_stack[-1][0] >= level:
                    path_stack.pop()
                path_stack.append((level, text))
                current_title = text
                current_path = " / ".join(item[1] for item in path_stack)
            else:
                buffer.append(text)

        flush_buffer()
        if not segments:
            raise DocumentParseError("DOCX 文件未提取到有效文本")
        return segments

    def _parse_pdf(self, path: Path) -> list[ParseSegment]:
        """PDF 基础解析：仅提取可复制文本，扫描件/OCR 不在本阶段范围。"""
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise DocumentParseError("缺少 pypdf 依赖，无法解析 pdf") from exc

        reader = PdfReader(str(path))
        segments: list[ParseSegment] = []
        for page_index, page in enumerate(reader.pages, start=1):
            raw = page.extract_text() or ""
            text = raw.strip()
            if not text:
                continue
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            if not paragraphs:
                paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
            for paragraph in paragraphs:
                segments.append(
                    ParseSegment(
                        text=paragraph,
                        section_title=f"第 {page_index} 页",
                        section_path=f"第 {page_index} 页",
                        page_no=page_index,
                    )
                )

        if not segments:
            raise DocumentParseError(
                "PDF 未提取到可复制文本，可能是扫描件或图片型 PDF，本阶段不支持 OCR"
            )
        return segments
