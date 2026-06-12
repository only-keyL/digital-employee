"""早期 Mock 规则匹配（阶段四遗留，RAG 上线前用于演示）。"""

from dataclasses import dataclass

from app.models.knowledge_card import KnowledgeCard

MOCK_SIMILARITY_SCORE = 0.86  # Mock 命中时的固定相似度分数
LOGIN_PERMISSION_CARD_TITLE = "登录失败提示账号无权限处理办法"  # 演示用固定卡片标题


@dataclass
class RuleMatchResult:
    """规则匹配结果。"""

    matched: bool  # 是否命中
    card: KnowledgeCard | None = None  # 命中的知识卡片
    similarity_score: float = 0.0  # 相似度分数


def should_attempt_match(question: str) -> bool:
    """判断是否应尝试规则匹配（含「登录」或「权限」关键词）。"""
    return ("登录" in question) or ("权限" in question)


def build_match_result(card: KnowledgeCard | None) -> RuleMatchResult:
    """根据卡片是否存在构造匹配结果。"""
    if card is None:
        return RuleMatchResult(matched=False, similarity_score=0.0)
    return RuleMatchResult(
        matched=True,
        card=card,
        similarity_score=MOCK_SIMILARITY_SCORE,
    )
