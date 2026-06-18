"""数字员工运营看板服务。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.repositories.operation_dashboard_repository import OperationDashboardRepository
from app.schemas.operation_dashboard_schema import (
    ConfidenceMetrics,
    DuplicateMetrics,
    FeedbackMetrics,
    KnowledgeMetrics,
    OperationDashboardSummary,
    OperationDashboardTops,
    QuestionMetrics,
    RiskCardItem,
    TopModuleItem,
    TopReferencedCardItem,
    TopUnansweredItem,
)


class OperationDashboardService:
    """数字员工运营看板服务。

    负责聚合问答日志、反馈日志、知识卡片和重复检测日志，输出后台运营看板需要的统计指标。
    本服务只做查询和聚合，不修改业务数据。
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = OperationDashboardRepository(session)

    def get_summary(self, *, days: int = 7) -> OperationDashboardSummary:
        """获取运营看板总览指标。"""
        duplicate_start = datetime.now() - timedelta(days=days) if days > 0 else None

        total_count = self.repo.count_questions()
        matched_count = self.repo.count_matched_questions()
        miss_count = max(total_count - matched_count, 0)

        # 分母为 0 时命中率返回 0，避免页面展示 NaN 或接口报错
        hit_rate = round(matched_count / total_count, 4) if total_count else 0.0

        confidence_raw = self.repo.get_confidence_distribution()
        feedback_raw = self.repo.get_feedback_distribution()
        knowledge_raw = self.repo.get_knowledge_status_distribution()
        duplicate_raw = self.repo.get_duplicate_distribution(start_time=duplicate_start)

        useful = feedback_raw.get("useful", 0)
        useless = feedback_raw.get("useless", 0)
        supplement = feedback_raw.get("supplement", 0)
        feedback_denominator = useful + useless
        effective_rate = round(useful / feedback_denominator, 4) if feedback_denominator else 0.0

        return OperationDashboardSummary(
            question=QuestionMetrics(
                today_count=self.repo.count_today_questions(),
                total_count=total_count,
                matched_count=matched_count,
                miss_count=miss_count,
                hit_rate=hit_rate,
                avg_latency_ms=self.repo.get_average_latency_ms(),
            ),
            confidence=ConfidenceMetrics(**confidence_raw),
            feedback=FeedbackMetrics(
                useful=useful,
                useless=useless,
                supplement=supplement,
                effective_rate=effective_rate,
            ),
            knowledge=KnowledgeMetrics(**knowledge_raw),
            duplicate=DuplicateMetrics(
                total=duplicate_raw.get("total", 0),
                high_duplicate=duplicate_raw.get("high_duplicate", 0),
                suspected_duplicate=duplicate_raw.get("suspected_duplicate", 0),
                related=duplicate_raw.get("related", 0),
                none=duplicate_raw.get("none", 0),
            ),
        )

    def get_top_lists(self, *, days: int = 7, limit: int = 10) -> OperationDashboardTops:
        """获取运营看板 Top 列表。"""
        start_time = datetime.now() - timedelta(days=days) if days > 0 else None

        return OperationDashboardTops(
            top_unanswered=[
                TopUnansweredItem(**item) for item in self.repo.list_top_unanswered(limit=limit)
            ],
            top_modules=[
                TopModuleItem(**item) for item in self.repo.list_top_modules(start_time=start_time, limit=limit)
            ],
            top_referenced_cards=[
                TopReferencedCardItem(**item)
                for item in self.repo.list_top_referenced_cards(start_time=start_time, limit=limit)
            ],
            risk_cards=[RiskCardItem(**item) for item in self.repo.list_risk_cards(limit=limit)],
        )

    def get_dashboard_view_model(self, *, days: int = 7) -> dict:
        """获取 Jinja2 页面渲染需要的完整视图模型。"""
        summary = self.get_summary(days=days)
        tops = self.get_top_lists(days=days)
        return {
            "days": days,
            "summary": summary.model_dump(),
            "tops": tops.model_dump(),
            "intro": (
                "本看板用于展示数字员工的问答效果、知识库质量、用户反馈和知识治理情况，"
                "帮助管理员持续优化企业知识库。"
            ),
        }
