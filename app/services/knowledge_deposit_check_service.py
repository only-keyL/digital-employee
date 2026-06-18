"""知识沉淀投稿检查：完整性、AI 质量、重复、风险。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.core.desensitize import sanitize_text
from app.infra.embedding_client import EmbeddingClient, EmbeddingClientError
from app.infra.llm_client import LLMInfraClient, LLMInfraError
from app.rag.qdrant_vector_store import QdrantVectorStore, get_qdrant_vector_store
from app.repositories.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)

# 完整性阈值
_MIN_QUESTION_LEN = 8
_MIN_ANSWER_LEN = 15
_MIN_SOLUTION_LEN = 15

# Qdrant 语义重复阈值
_QDRANT_STRONG_DUPLICATE = 0.88
_QDRANT_POSSIBLE_DUPLICATE = 0.78

# 敏感信息正则
_PHONE_RE = re.compile(r"1[3-9]\d{9}")
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_ID_CARD_RE = re.compile(r"\d{17}[\dXx]|\d{15}")
_API_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|secret|bearer)\s*[:=]\s*\S{8,}")
_PASSWORD_RE = re.compile(r"(?i)(password|密码)\s*[:=]\s*\S+")
_DB_CONN_RE = re.compile(r"(?i)(mysql|postgresql|mongodb)://\S+")

# 高风险关键词
_HIGH_RISK_KEYWORDS = (
    "删除生产库",
    "drop table",
    "truncate table",
    "rm -rf",
    "强制删除数据",
    "绕过审批",
    "修改生产权限",
    "批量授权",
    "关闭审计",
    "关闭备份",
)

_AI_CHECK_PROMPT = """你是企业内部知识库审核助手。请评估下面这条知识卡片是否适合入库。
只返回 JSON，不要其他文字：
{{
  "passed": true/false,
  "score": 0.0-1.0,
  "missing": ["缺失项"],
  "suggestions": ["建议"],
  "reason": "一句话说明"
}}

评估标准：
1. 是否像可复用知识
2. 问题是否清晰
3. 答案是否能指导排查
4. 是否缺少关键上下文
5. 是否明显闲聊/抱怨/无效内容

【知识卡片】
标题：{title}
问题：{question}
答案：{answer}
解决方案：{solution}
"""


@dataclass
class CompletenessResult:
    passed: bool
    score: float
    missing_fields: list[str]
    reasons: list[str] = field(default_factory=list)


@dataclass
class AiCheckResult:
    passed: bool
    score: float
    missing: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    reason: str = ""
    error: str | None = None


@dataclass
class DuplicateCheckResult:
    duplicate_suspected: bool
    duplicate_possible: bool
    mysql_matches: list[dict] = field(default_factory=list)
    qdrant_matches: list[dict] = field(default_factory=list)
    top_score: float = 0.0
    skipped: bool = False
    message: str = ""


@dataclass
class RiskCheckResult:
    risk_level: str  # none / low / medium / high
    hits: list[str] = field(default_factory=list)
    blocked: bool = False
    message: str = ""


class KnowledgeDepositCheckService:
    """知识投稿多维度检查服务。"""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: QdrantVectorStore | None = None,
        llm_client: LLMInfraClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.knowledge_repo = KnowledgeRepository(session)
        self.embedding = embedding_client or EmbeddingClient(self.settings)
        self.store = vector_store or get_qdrant_vector_store()
        self.llm = llm_client or LLMInfraClient(self.settings)

    def check_completeness(self, parsed_card: dict, missing_fields: list[str]) -> CompletenessResult:
        """规则完整性检查：必填字段与最小长度。"""
        reasons: list[str] = list(missing_fields)
        question = (parsed_card.get("question") or "").strip()
        answer = (parsed_card.get("answer") or "").strip()
        solution = (parsed_card.get("solution") or "").strip()
        tags = (parsed_card.get("tags") or "").strip()

        if len(question) < _MIN_QUESTION_LEN:
            reasons.append("问题过短")
        if len(answer) < _MIN_ANSWER_LEN:
            reasons.append("答案过短")
        if len(solution) < _MIN_SOLUTION_LEN:
            reasons.append("解决方案过短")
        if not tags:
            reasons.append("标签为空")

        total_required = 8
        filled = total_required - len(missing_fields)
        score = max(0.0, min(1.0, filled / total_required))
        passed = len(reasons) == 0
        return CompletenessResult(passed=passed, score=score, missing_fields=reasons, reasons=reasons)

    async def ai_quality_check(self, parsed_card: dict) -> AiCheckResult:
        """DeepSeek AI 质量检查，失败时不自动通过。"""
        prompt = _AI_CHECK_PROMPT.format(
            title=sanitize_text(parsed_card.get("title", ""), max_length=100),
            question=sanitize_text(parsed_card.get("question", ""), max_length=200),
            answer=sanitize_text(parsed_card.get("answer", ""), max_length=200),
            solution=sanitize_text(parsed_card.get("solution", ""), max_length=200),
        )
        try:
            client = self.llm._get_client()
            response = await client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=512,
            )
            raw = (response.choices[0].message.content or "").strip()
            data = self._parse_ai_json(raw)
            return AiCheckResult(
                passed=bool(data.get("passed")),
                score=float(data.get("score", 0.0)),
                missing=list(data.get("missing") or []),
                suggestions=list(data.get("suggestions") or []),
                reason=str(data.get("reason") or ""),
            )
        except (LLMInfraError, Exception) as exc:
            logger.error("AI 质量检查失败：%s", exc)
            return AiCheckResult(
                passed=False,
                score=0.0,
                reason="AI 质量检查暂时不可用，请稍后重试",
                error=str(exc),
            )

    @staticmethod
    def _parse_ai_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)

    def check_mysql_duplicate(self, parsed_card: dict) -> DuplicateCheckResult:
        """MySQL 重复检查：标题完全相同或问题高度相似。"""
        title = (parsed_card.get("title") or "").strip()
        question = (parsed_card.get("question") or "").strip()
        system_name = (parsed_card.get("system_name") or "").strip()
        module_name = (parsed_card.get("module_name") or "").strip()
        tags = (parsed_card.get("tags") or "").strip()

        matches: list[dict] = []
        duplicate_suspected = False

        if title:
            existing = self.knowledge_repo.get_by_title(title)
            if existing is not None:
                duplicate_suspected = True
                matches.append(self._card_summary(existing, reason="title_exact"))

        cards = self.knowledge_repo.list_approved_enabled()
        for card in cards:
            if card.question and question:
                ratio = SequenceMatcher(None, question, card.question).ratio()
                if ratio >= 0.85:
                    duplicate_suspected = True
                    matches.append(self._card_summary(card, reason=f"question_similarity={ratio:.2f}"))
                    continue
            if (
                system_name
                and module_name
                and card.system_name == system_name
                and card.module_name == module_name
                and tags
                and card.tags
            ):
                tag_overlap = len(set(tags.split(",")) & set(card.tags.split(",")))
                if tag_overlap >= 2 and title and card.title:
                    title_ratio = SequenceMatcher(None, title, card.title).ratio()
                    if title_ratio >= 0.7:
                        duplicate_suspected = True
                        matches.append(self._card_summary(card, reason="system_module_tags_overlap"))

        return DuplicateCheckResult(
            duplicate_suspected=duplicate_suspected,
            duplicate_possible=False,
            mysql_matches=matches[:5],
        )

    async def check_qdrant_duplicate(self, parsed_card: dict) -> DuplicateCheckResult:
        """Qdrant 语义重复检查：只 search 不写入。"""
        text = "\n".join(
            [
                parsed_card.get("title") or "",
                parsed_card.get("question") or "",
                parsed_card.get("solution") or "",
            ]
        ).strip()
        if not text:
            return DuplicateCheckResult(
                duplicate_suspected=False,
                duplicate_possible=False,
                skipped=True,
                message="无有效文本，跳过 Qdrant 重复检查",
            )
        try:
            vector = await self.embedding.embed_text(text)
            hits = self.store.search(vector, top_k=3, score_threshold=None)
        except EmbeddingClientError as exc:
            logger.warning("Qdrant 重复检查 embedding 失败：%s", exc)
            return DuplicateCheckResult(
                duplicate_suspected=False,
                duplicate_possible=False,
                skipped=True,
                message=f"duplicate_check_skipped: {exc}",
            )
        except Exception as exc:
            logger.warning("Qdrant 重复检查失败：%s", exc)
            return DuplicateCheckResult(
                duplicate_suspected=False,
                duplicate_possible=False,
                skipped=True,
                message=f"duplicate_check_skipped: {exc}",
            )

        if not hits:
            return DuplicateCheckResult(
                duplicate_suspected=False,
                duplicate_possible=False,
                skipped=False,
                message="collection 无命中",
            )

        top_score = float(hits[0].get("score", 0.0))
        qdrant_matches = []
        for hit in hits:
            payload = hit.get("payload") or {}
            qdrant_matches.append(
                {
                    "knowledge_id": hit.get("knowledge_id"),
                    "score": hit.get("score"),
                    "title": payload.get("title", ""),
                    "question_preview": payload.get("question_preview", ""),
                }
            )

        duplicate_suspected = top_score >= _QDRANT_STRONG_DUPLICATE
        duplicate_possible = _QDRANT_POSSIBLE_DUPLICATE <= top_score < _QDRANT_STRONG_DUPLICATE
        return DuplicateCheckResult(
            duplicate_suspected=duplicate_suspected,
            duplicate_possible=duplicate_possible,
            qdrant_matches=qdrant_matches,
            top_score=top_score,
        )

    def check_risk(self, parsed_card: dict, raw_content: str) -> RiskCheckResult:
        """敏感信息与高风险操作检查。"""
        blob = raw_content + "\n" + json.dumps(parsed_card, ensure_ascii=False)
        hits: list[str] = []

        if _PHONE_RE.search(blob):
            hits.append("检测到手机号")
        if _EMAIL_RE.search(blob):
            hits.append("检测到邮箱")
        if _ID_CARD_RE.search(blob):
            hits.append("检测到身份证号")
        if _API_KEY_RE.search(blob):
            hits.append("检测到疑似 API Key/Token")
        if _PASSWORD_RE.search(blob):
            hits.append("检测到密码字样")
        if _DB_CONN_RE.search(blob):
            hits.append("检测到数据库连接串")

        lower_blob = blob.lower()
        for kw in _HIGH_RISK_KEYWORDS:
            if kw.lower() in lower_blob:
                hits.append(f"高风险操作：{kw}")

        if any("高风险操作" in h for h in hits):
            return RiskCheckResult(
                risk_level="high",
                hits=hits,
                blocked=True,
                message="该内容涉及高风险操作，已进入风险拦截，需要管理员人工确认。",
            )
        if hits:
            return RiskCheckResult(
                risk_level="medium",
                hits=hits,
                blocked=True,
                message="检测到敏感信息，请脱敏后重新提交。",
            )
        return RiskCheckResult(risk_level="none", hits=[], blocked=False)

    @staticmethod
    def _card_summary(card, *, reason: str) -> dict:
        return {
            "knowledge_id": card.id,
            "title": card.title,
            "question_preview": sanitize_text(card.question or "", max_length=80),
            "reason": reason,
        }
