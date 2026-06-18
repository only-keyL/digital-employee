"""运营看板统计查询 Repository（只读）。"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.feedback_log import FeedbackLog
from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.models.question_log import QuestionLog
from app.models.unanswered_question import UnansweredQuestion


class OperationDashboardRepository:
    """运营看板统计查询 Repository。

    集中封装 question_log、feedback_log、knowledge_card、duplicate_check_log 等表的只读统计查询。
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def count_questions(self, *, start_time: datetime | None = None) -> int:
        """统计问题数量。"""
        stmt = select(func.count(QuestionLog.id))
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        return int(self.session.scalar(stmt) or 0)

    def count_today_questions(self) -> int:
        """统计今日提问数。"""
        today_start = datetime.combine(datetime.now().date(), time.min)
        return self.count_questions(start_time=today_start)

    def count_matched_questions(self, *, start_time: datetime | None = None) -> int:
        """统计命中问题数量（matched=1）。"""
        stmt = select(func.count(QuestionLog.id)).where(QuestionLog.matched == 1)
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        return int(self.session.scalar(stmt) or 0)

    def get_confidence_distribution(self, *, start_time: datetime | None = None) -> dict[str, int]:
        """统计置信度分布。"""
        stmt = select(QuestionLog.confidence_level, func.count(QuestionLog.id)).group_by(
            QuestionLog.confidence_level
        )
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        rows = self.session.execute(stmt).all()
        result = {"high": 0, "medium": 0, "low": 0, "none": 0}
        for level, count in rows:
            key = (level or "none").lower()
            if key in result:
                result[key] = int(count or 0)
            else:
                result["none"] += int(count or 0)
        return result

    def get_average_latency_ms(self, *, start_time: datetime | None = None) -> float | None:
        """统计平均响应耗时（跳过空值）。"""
        stmt = select(func.avg(QuestionLog.latency_ms)).where(QuestionLog.latency_ms.isnot(None))
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        value = self.session.scalar(stmt)
        return round(float(value), 2) if value is not None else None

    def get_feedback_distribution(self, *, start_time: datetime | None = None) -> dict[str, int]:
        """统计反馈类型分布。"""
        stmt = select(FeedbackLog.feedback_type, func.count(FeedbackLog.id)).group_by(
            FeedbackLog.feedback_type
        )
        if start_time is not None:
            stmt = stmt.where(FeedbackLog.create_time >= start_time)
        rows = self.session.execute(stmt).all()
        result = {"useful": 0, "useless": 0, "supplement": 0}
        for fb_type, count in rows:
            if fb_type in result:
                result[fb_type] = int(count or 0)
        return result

    def get_knowledge_status_distribution(self) -> dict[str, int]:
        """统计知识卡片审核状态分布。"""
        def _count_where(*conditions) -> int:
            stmt = select(func.count(KnowledgeCard.id)).where(
                KnowledgeCard.deleted == 0,
                *conditions,
            )
            return int(self.session.scalar(stmt) or 0)

        return {
            "total": _count_where(),
            "approved": _count_where(KnowledgeCard.audit_status == "approved"),
            "pending": _count_where(KnowledgeCard.audit_status == "pending"),
            "draft": _count_where(KnowledgeCard.audit_status == "draft"),
            "rejected": _count_where(KnowledgeCard.audit_status == "rejected"),
            "enabled": _count_where(KnowledgeCard.enabled == 1),
            "need_review": _count_where(KnowledgeCard.need_review == 1),
        }

    def get_duplicate_distribution(self, *, start_time: datetime | None = None) -> dict[str, int]:
        """统计重复检测等级分布。"""
        stmt = select(
            KnowledgeDuplicateCheckLog.check_level,
            func.count(KnowledgeDuplicateCheckLog.id),
        ).group_by(KnowledgeDuplicateCheckLog.check_level)
        if start_time is not None:
            stmt = stmt.where(KnowledgeDuplicateCheckLog.created_at >= start_time)
        rows = self.session.execute(stmt).all()
        result = {
            "total": 0,
            "high_duplicate": 0,
            "suspected_duplicate": 0,
            "related": 0,
            "none": 0,
        }
        for level, count in rows:
            cnt = int(count or 0)
            result["total"] += cnt
            key = level or "none"
            if key in result:
                result[key] = cnt
            else:
                result["none"] += cnt
        return result

    def list_top_unanswered(self, *, limit: int = 10) -> list[dict]:
        """查询高频未命中问题。"""
        stmt = (
            select(UnansweredQuestion)
            .order_by(UnansweredQuestion.frequency.desc(), UnansweredQuestion.last_seen_time.desc())
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt).all())
        return [
            {
                "id": row.id,
                "question": row.summary or row.question or "",
                "frequency": int(row.frequency or 0),
                "status": row.status or "",
                "last_seen_time": row.last_seen_time.isoformat() if row.last_seen_time else None,
            }
            for row in rows
        ]

    def list_top_modules(self, *, start_time: datetime | None = None, limit: int = 10) -> list[dict]:
        """查询高频系统/模块。"""
        stmt = (
            select(
                QuestionLog.system_name,
                QuestionLog.module_name,
                func.count(QuestionLog.id).label("ask_count"),
            )
            .where(QuestionLog.system_name.isnot(None))
            .group_by(QuestionLog.system_name, QuestionLog.module_name)
            .order_by(func.count(QuestionLog.id).desc())
            .limit(limit)
        )
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        rows = self.session.execute(stmt).all()
        return [
            {
                "system_name": row.system_name or "",
                "module_name": row.module_name or "",
                "ask_count": int(row.ask_count or 0),
            }
            for row in rows
        ]

    def list_top_referenced_cards(
        self, *, start_time: datetime | None = None, limit: int = 10
    ) -> list[dict]:
        """查询最常被引用的知识卡片。"""
        stmt = (
            select(
                QuestionLog.primary_matched_card_id,
                QuestionLog.primary_matched_card_title,
                func.count(QuestionLog.id).label("reference_count"),
                func.max(QuestionLog.create_time).label("last_reference_time"),
            )
            .where(QuestionLog.primary_matched_card_id.isnot(None))
            .group_by(QuestionLog.primary_matched_card_id, QuestionLog.primary_matched_card_title)
            .order_by(func.count(QuestionLog.id).desc())
            .limit(limit)
        )
        if start_time is not None:
            stmt = stmt.where(QuestionLog.create_time >= start_time)
        rows = self.session.execute(stmt).all()
        return [
            {
                "card_id": int(row.primary_matched_card_id or 0),
                "title": row.primary_matched_card_title or "",
                "reference_count": int(row.reference_count or 0),
                "last_reference_time": (
                    row.last_reference_time.isoformat() if row.last_reference_time else None
                ),
            }
            for row in rows
        ]

    def list_risk_cards(self, *, limit: int = 10) -> list[dict]:
        """查询风险知识卡片。"""
        stmt = (
            select(KnowledgeCard)
            .where(KnowledgeCard.deleted == 0)
            .order_by(
                KnowledgeCard.need_review.desc(),
                KnowledgeCard.useless_count.desc(),
                KnowledgeCard.supplement_count.desc(),
                KnowledgeCard.quality_score.asc(),
            )
            .limit(limit)
        )
        rows = list(self.session.scalars(stmt).all())
        return [
            {
                "card_id": row.id,
                "title": row.title or "",
                "system_name": row.system_name,
                "module_name": row.module_name,
                "useful_count": int(row.useful_count or 0),
                "useless_count": int(row.useless_count or 0),
                "supplement_count": int(row.supplement_count or 0),
                "quality_score": float(row.quality_score) if row.quality_score is not None else None,
                "need_review": int(row.need_review or 0),
            }
            for row in rows
        ]
