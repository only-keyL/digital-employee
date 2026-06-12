"""知识卡片正文拼接与内容哈希（供向量同步与去重使用）。"""

import hashlib
from typing import Any


def build_knowledge_content_text(data: dict[str, Any]) -> str:
    """按固定格式拼接知识卡片全文（用于 content_hash 与 Qdrant embedding）。"""
    return (
        f"标题：{data.get('title') or ''}\n"
        f"标准问题：{data.get('question') or ''}\n"
        f"标准答案：{data.get('answer') or ''}\n"
        f"所属系统：{data.get('system_name') or ''}\n"
        f"所属模块：{data.get('module_name') or ''}\n"
        f"标签：{data.get('tags') or ''}\n"
        f"适用场景：{data.get('scene') or ''}\n"
        f"原因分析：{data.get('reason_analysis') or ''}\n"
        f"排查步骤：{data.get('troubleshooting_steps') or ''}\n"
        f"解决方案：{data.get('solution') or ''}\n"
        f"风险提醒：{data.get('risk_notice') or ''}"
    )


def compute_content_hash(data: dict[str, Any]) -> str:
    """计算知识卡片内容的 SHA256 哈希。"""
    text = build_knowledge_content_text(data)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def card_to_content_dict(card: Any) -> dict[str, Any]:
    """将 ORM 知识卡片对象转为 content 字典。"""
    return {
        "title": card.title,
        "question": card.question,
        "answer": card.answer,
        "system_name": card.system_name,
        "module_name": card.module_name,
        "tags": card.tags,
        "scene": card.scene,
        "reason_analysis": card.reason_analysis,
        "troubleshooting_steps": card.troubleshooting_steps,
        "solution": card.solution,
        "risk_notice": card.risk_notice,
    }
