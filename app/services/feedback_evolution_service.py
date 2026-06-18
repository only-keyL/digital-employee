"""回答反馈与知识进化服务：有用 / 无用 / 补充反馈闭环。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.feedback_log import FeedbackLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_card_revision import KnowledgeCardRevision
from app.models.question_log import QuestionLog
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.knowledge_card_revision_repository import KnowledgeCardRevisionRepository
from app.repositories.knowledge_repository import KnowledgeRepository
from app.repositories.question_repository import QuestionRepository
from app.schemas.feedback_schema import FeedbackSubmitRequest

# 可绑定反馈的问答状态
_FEEDBACK_ANSWER_STATUSES = (
    "hit",
    "medium_confidence",
    "low_confidence",
    "miss",
    "llm_failed",
    "error",
)

# 文本指令：有用
_USEFUL_EXACT = frozenset({"有用", "已解决", "解决"})

# 文本指令：无用（整句匹配）
_USELESS_EXACT = frozenset({"无用", "没用", "未解决", "答非所问"})

# 文本指令：无用（带原因前缀）
_USELESS_PREFIXES = ("无用：", "无用:", "没用：", "没用:", "未解决：", "未解决:")

# 文本指令：补充 / 纠错
_SUPPLEMENT_PREFIXES = ("补充：", "补充:", "纠错：", "纠错:", "补充答案：", "补充答案:")

# 无用原因类型映射关键词
_REASON_TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("答非所问", "irrelevant"),
    ("步骤不完整", "incomplete"),
    ("答案过期", "outdated"),
    ("当前场景不适用", "not_applicable"),
    ("仍然解决不了", "unresolved"),
    ("未解决", "unresolved"),
)

_USELESS_REVIEW_COUNT = 3
_QUALITY_REVIEW_THRESHOLD = Decimal("0.6")


class FeedbackEvolutionError(Exception):
    """反馈闭环业务异常。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass
class ParsedFeedback:
    """企微文本反馈解析结果。"""

    feedback_type: str
    reason_text: str | None = None
    reason_type: str | None = None
    supplement_text: str | None = None


@dataclass
class FeedbackSubmitResult:
    """反馈提交结果。"""

    feedback_id: int
    question_log_id: int
    knowledge_card_id: int | None
    feedback_type: str
    revision_id: int | None
    message: str

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "question_log_id": self.question_log_id,
            "knowledge_card_id": self.knowledge_card_id,
            "feedback_type": self.feedback_type,
            "revision_id": self.revision_id,
        }


class FeedbackEvolutionService:
    """回答反馈与知识进化服务。

    负责处理用户对数字员工回答的有用、无用、补充反馈。
    本服务只记录反馈、更新质量计数、生成修订建议，不直接修改正式知识卡片内容。
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.feedback_repo = FeedbackRepository(session)
        self.question_repo = QuestionRepository(session)
        self.knowledge_repo = KnowledgeRepository(session)
        self.revision_repo = KnowledgeCardRevisionRepository(session)

    def submit_feedback(self, request: FeedbackSubmitRequest) -> FeedbackSubmitResult:
        """提交用户反馈，自动绑定问答日志并执行对应处理。"""
        if request.feedback_type not in {"useful", "useless", "supplement"}:
            raise FeedbackEvolutionError("反馈类型非法")

        if request.feedback_type == "supplement":
            supplement_text = (request.supplement_text or "").strip()
            if not supplement_text:
                raise FeedbackEvolutionError("请在「补充：」后填写你认为更准确的处理方案。")

        question_log = self.find_feedback_target(
            user_id=request.user_id,
            group_id=request.group_id,
            question_log_id=request.question_log_id,
        )

        if request.feedback_type == "useful":
            return self.handle_useful(question_log, request)
        if request.feedback_type == "useless":
            return self.handle_useless(question_log, request)
        return self.handle_supplement(question_log, request)

    def submit_text_feedback(
        self,
        *,
        text: str,
        user_id: str,
        group_id: str | None,
    ) -> FeedbackSubmitResult:
        """识别企微文本反馈并提交。"""
        parsed = self.parse_text_feedback(text)
        if parsed is None:
            raise FeedbackEvolutionError("无法识别的反馈指令")

        request = FeedbackSubmitRequest(
            user_id=user_id,
            group_id=group_id,
            feedback_type=parsed.feedback_type,  # type: ignore[arg-type]
            reason_type=parsed.reason_type,
            reason_text=parsed.reason_text,
            supplement_text=parsed.supplement_text,
        )
        return self.submit_feedback(request)

    @staticmethod
    def parse_text_feedback(text: str) -> ParsedFeedback | None:
        """识别企微文本反馈指令，例如：有用、无用：原因、补充：正确答案。"""
        content = (text or "").strip()
        if not content:
            return None

        if content in _USEFUL_EXACT:
            return ParsedFeedback(feedback_type="useful")

        for prefix in _USELESS_PREFIXES:
            if content.startswith(prefix):
                reason_text = content[len(prefix) :].strip() or None
                return ParsedFeedback(
                    feedback_type="useless",
                    reason_text=reason_text,
                    reason_type=FeedbackEvolutionService._infer_reason_type(reason_text, content),
                )

        if content in _USELESS_EXACT:
            return ParsedFeedback(
                feedback_type="useless",
                reason_type=FeedbackEvolutionService._infer_reason_type(None, content),
            )

        for prefix in _SUPPLEMENT_PREFIXES:
            if content.startswith(prefix):
                supplement_text = content[len(prefix) :].strip()
                return ParsedFeedback(
                    feedback_type="supplement",
                    supplement_text=supplement_text or None,
                )

        return None

    @staticmethod
    def is_feedback_text(text: str) -> bool:
        """判断文本是否为反馈指令（供路由层优先识别）。"""
        return FeedbackEvolutionService.parse_text_feedback(text) is not None

    def find_feedback_target(
        self,
        *,
        user_id: str,
        group_id: str | None,
        question_log_id: int | None = None,
        within_minutes: int = 30,
    ) -> QuestionLog:
        """查找反馈要绑定的问答日志。"""
        if question_log_id is not None:
            log = self.question_repo.get_log_by_id(question_log_id)
            if log is None:
                raise FeedbackEvolutionError("指定的问答日志不存在")
            return log

        log = self.question_repo.get_latest_feedback_target(
            user_id=user_id,
            group_id=group_id,
            within_minutes=within_minutes,
        )
        if log is None:
            raise FeedbackEvolutionError("未找到可绑定的最近问答，请先向数字员工提问后再反馈。")
        return log

    def handle_useful(self, question_log: QuestionLog, request: FeedbackSubmitRequest) -> FeedbackSubmitResult:
        """处理有用反馈。"""
        card_id = question_log.primary_matched_card_id
        feedback = self._create_feedback_record(
            question_log=question_log,
            request=request,
            feedback_type="useful",
        )

        if card_id is not None:
            card = self.knowledge_repo.get_active_by_id(card_id)
            if card is not None:
                self.knowledge_repo.update_feedback_stats(card, feedback_type="useful")
                self.recalculate_quality_score(card)

        self.feedback_repo.save()
        return FeedbackSubmitResult(
            feedback_id=feedback.id,
            question_log_id=question_log.id,
            knowledge_card_id=card_id,
            feedback_type="useful",
            revision_id=None,
            message="已记录，本次回答被标记为有用。感谢反馈。",
        )

    def handle_useless(self, question_log: QuestionLog, request: FeedbackSubmitRequest) -> FeedbackSubmitResult:
        """处理无用反馈。"""
        card_id = question_log.primary_matched_card_id
        reason_text = (request.reason_text or request.comment or "").strip() or None
        reason_type = request.reason_type or self._infer_reason_type(reason_text, reason_text or "")

        feedback = self._create_feedback_record(
            question_log=question_log,
            request=request,
            feedback_type="useless",
            reason_type=reason_type,
            reason_text=reason_text,
        )

        if card_id is not None:
            card = self.knowledge_repo.get_active_by_id(card_id)
            if card is not None:
                self.knowledge_repo.update_feedback_stats(card, feedback_type="useless")
                self.recalculate_quality_score(card)

        self.feedback_repo.save()
        return FeedbackSubmitResult(
            feedback_id=feedback.id,
            question_log_id=question_log.id,
            knowledge_card_id=card_id,
            feedback_type="useless",
            revision_id=None,
            message="已记录，本次回答被标记为无用。管理员后续可以根据反馈优化知识卡片。",
        )

    def handle_supplement(self, question_log: QuestionLog, request: FeedbackSubmitRequest) -> FeedbackSubmitResult:
        """处理补充/纠错反馈，并生成知识修订建议。"""
        supplement_text = (request.supplement_text or "").strip()
        if not supplement_text:
            raise FeedbackEvolutionError("请在「补充：」后填写你认为更准确的处理方案。")

        card_id = question_log.primary_matched_card_id
        feedback = self._create_feedback_record(
            question_log=question_log,
            request=request,
            feedback_type="supplement",
            supplement_text=supplement_text,
        )

        revision = self._create_revision_from_supplement(
            question_log=question_log,
            feedback=feedback,
            supplement_text=supplement_text,
            submit_user=request.user_id,
        )

        if card_id is not None:
            card = self.knowledge_repo.get_active_by_id(card_id)
            if card is not None:
                self.knowledge_repo.update_feedback_stats(card, feedback_type="supplement")

        self.feedback_repo.save()
        return FeedbackSubmitResult(
            feedback_id=feedback.id,
            question_log_id=question_log.id,
            knowledge_card_id=card_id,
            feedback_type="supplement",
            revision_id=revision.id,
            message="已收到你的补充内容，并生成知识修订建议。管理员确认后可提交审核。",
        )

    def recalculate_quality_score(self, card: KnowledgeCard) -> None:
        """根据有用/无用次数重新计算知识卡片质量分。"""
        total = int(card.useful_count or 0) + int(card.useless_count or 0)
        if total <= 0:
            card.quality_score = None
        else:
            card.quality_score = Decimal(str(round(card.useful_count / total, 4)))

        # 无用反馈过多且质量分偏低时，标记需要复核
        if (
            int(card.useless_count or 0) >= _USELESS_REVIEW_COUNT
            and card.quality_score is not None
            and card.quality_score < _QUALITY_REVIEW_THRESHOLD
        ):
            card.need_review = 1

        self.session.flush()

    def _create_feedback_record(
        self,
        *,
        question_log: QuestionLog,
        request: FeedbackSubmitRequest,
        feedback_type: str,
        reason_type: str | None = None,
        reason_text: str | None = None,
        supplement_text: str | None = None,
    ) -> FeedbackLog:
        """写入 feedback_log 记录。"""
        record = FeedbackLog(
            question_log_id=question_log.id,
            user_id=(request.user_id or "anonymous").strip() or "anonymous",
            feedback_type=feedback_type,
            comment=request.comment,
            knowledge_card_id=question_log.primary_matched_card_id,
            group_id=request.group_id or question_log.group_id,
            reason_type=reason_type,
            reason_text=reason_text,
            supplement_text=supplement_text,
            status="new",
        )
        return self.feedback_repo.create(record)

    def _create_revision_from_supplement(
        self,
        *,
        question_log: QuestionLog,
        feedback: FeedbackLog,
        supplement_text: str,
        submit_user: str,
    ) -> KnowledgeCardRevision:
        """补充反馈只生成修订建议，不直接修改正式知识卡片。"""
        question_text = (
            question_log.rewritten_question or question_log.question_raw or question_log.question_masked or ""
        ).strip()
        card_id = question_log.primary_matched_card_id

        if card_id is not None:
            card = self.knowledge_repo.get_active_by_id(card_id)
            proposed_title = card.title if card else question_log.primary_matched_card_title
            revision = KnowledgeCardRevision(
                source_feedback_id=feedback.id,
                original_card_id=card_id,
                revision_type="update_existing",
                proposed_title=proposed_title,
                proposed_question=question_text,
                proposed_answer=supplement_text,
                proposed_solution=supplement_text,
                status="draft",
                submit_user=submit_user,
            )
        else:
            title_base = question_text[:30] if question_text else "用户补充"
            revision = KnowledgeCardRevision(
                source_feedback_id=feedback.id,
                original_card_id=None,
                revision_type="create_new",
                proposed_title=f"用户补充：{title_base}",
                proposed_question=question_text,
                proposed_answer=supplement_text,
                proposed_solution=supplement_text,
                status="draft",
                submit_user=submit_user,
            )

        return self.revision_repo.create(revision)

    @staticmethod
    def _infer_reason_type(reason_text: str | None, full_text: str) -> str | None:
        """根据用户填写内容推断无用原因类型。"""
        blob = f"{reason_text or ''} {full_text or ''}"
        for keyword, reason_type in _REASON_TYPE_RULES:
            if keyword in blob:
                return reason_type
        if reason_text or full_text in _USELESS_EXACT:
            return "other"
        return None
