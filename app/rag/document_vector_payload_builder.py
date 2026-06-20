"""文档切片向量文本与 Qdrant payload 构建。"""

from __future__ import annotations

from typing import Any

from app.models.document_chunk import DocumentChunk
from app.models.document_source import DocumentSource

# 文档切片 Qdrant point id 偏移，避免与知识卡片 id 冲突
DOCUMENT_QDRANT_ID_OFFSET = 10_000_000_000


def qdrant_point_id_for_chunk(chunk_id: int) -> int:
    """将 chunk_id 映射为 Qdrant 数值 point id。"""
    return DOCUMENT_QDRANT_ID_OFFSET + int(chunk_id)


def vector_id_for_chunk(chunk_id: int) -> str:
    """MySQL vector_id 字段：便于排查与删除。"""
    return f"doc_chunk_{chunk_id}"


def is_sync_eligible_chunk(chunk: DocumentChunk, doc: DocumentSource) -> bool:
    """仅同步已解析、启用且未删除的文档及其有效切片。"""
    if doc.deleted != 0 or doc.enabled != 1 or doc.parse_status != "parsed":
        return False
    if chunk.deleted != 0 or chunk.enabled != 1:
        return False
    return bool((chunk.content or "").strip())


def build_document_chunk_vector_text(chunk: DocumentChunk, doc: DocumentSource) -> str:
    """向量文本携带文档名/系统/模块/章节，提升检索召回与来源可追溯性。"""
    page_line = f"页码：{chunk.page_no}" if chunk.page_no else "页码："
    return (
        f"文档：《{doc.doc_name}》\n"
        f"文档类型：{doc.doc_type or ''}\n"
        f"系统：{doc.system_name or ''}\n"
        f"模块：{doc.module_name or ''}\n"
        f"章节：{chunk.section_path or chunk.section_title or ''}\n"
        f"{page_line}\n\n"
        f"正文：\n{chunk.content or ''}"
    )


def build_document_chunk_payload(chunk: DocumentChunk, doc: DocumentSource) -> dict[str, Any]:
    """Qdrant payload 只存摘要字段，完整正文留在 MySQL chunk.content。"""
    return {
        "source_type": "document_chunk",
        "doc_id": doc.id,
        "chunk_id": chunk.id,
        "doc_name": doc.doc_name,
        "doc_type": doc.doc_type or "",
        "system_name": doc.system_name or "",
        "module_name": doc.module_name or "",
        "section_title": chunk.section_title or "",
        "section_path": chunk.section_path or "",
        "page_no": chunk.page_no,
        "chunk_index": chunk.chunk_index,
        "content_hash": chunk.content_hash or "",
    }
