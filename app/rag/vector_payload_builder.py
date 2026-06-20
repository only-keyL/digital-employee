"""Stage3 向量 payload 构建：向量文本可含正文，payload 仅保存摘要字段。"""

from __future__ import annotations

from typing import Any

from app.core.desensitize import sanitize_text
from app.models.knowledge_card import KnowledgeCard
from app.services.knowledge_content import build_knowledge_content_text, card_to_content_dict


def is_sync_eligible(card: KnowledgeCard) -> bool:
    """仅 approved + enabled + 未删除 的知识可同步 Qdrant。"""
    return card.deleted == 0 and card.audit_status == "approved" and card.enabled == 1


def build_vector_text(card: KnowledgeCard) -> str:
    """拼接用于 embedding 的全文（可包含知识正文）。"""
    data = card_to_content_dict(card)
    return (
        f"标题：{data.get('title') or ''}\n"
        f"问题：{data.get('question') or ''}\n"
        f"答案：{data.get('answer') or ''}\n"
        f"系统：{data.get('system_name') or ''}\n"
        f"模块：{data.get('module_name') or ''}\n"
        f"标签：{data.get('tags') or ''}\n"
        f"场景：{data.get('scene') or ''}\n"
        f"原因分析：{data.get('reason_analysis') or ''}\n"
        f"排查步骤：{data.get('troubleshooting_steps') or ''}\n"
        f"解决方案：{data.get('solution') or ''}\n"
        f"风险提示：{data.get('risk_notice') or ''}"
    )


def build_qdrant_payload(card: KnowledgeCard) -> dict[str, Any]:
    """构建 Qdrant payload：不保存完整答案正文。"""
    question_preview = sanitize_text(card.question or card.title or "", max_length=120)
    return {
        "source_type": "knowledge_card",
        "knowledge_id": card.id,
        "title": card.title,
        "question_preview": question_preview,
        "system_name": card.system_name or "",
        "module_name": card.module_name or "",
        "tags": card.tags or "",
        "version": card.version,
        "content_hash": card.content_hash or "",
        "updated_at": card.update_time.isoformat() if card.update_time else "",
    }
