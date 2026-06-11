from dataclasses import dataclass

from app.models.knowledge_card import KnowledgeCard

MOCK_SIMILARITY_SCORE = 0.86
LOGIN_PERMISSION_CARD_TITLE = "登录失败提示账号无权限处理办法"


@dataclass
class RuleMatchResult:
    matched: bool
    card: KnowledgeCard | None = None
    similarity_score: float = 0.0


def should_attempt_match(question: str) -> bool:
    return ("登录" in question) or ("权限" in question)


def build_match_result(card: KnowledgeCard | None) -> RuleMatchResult:
    if card is None:
        return RuleMatchResult(matched=False, similarity_score=0.0)
    return RuleMatchResult(
        matched=True,
        card=card,
        similarity_score=MOCK_SIMILARITY_SCORE,
    )
