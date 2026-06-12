from sqlalchemy.orm import Session

from app.repositories.statistics_repository import StatisticsRepository


class StatisticsService:
    """运营统计看板数据聚合服务。"""

    def __init__(self, session: Session) -> None:
        self.repo = StatisticsRepository(session)

    def get_dashboard(self) -> dict:
        data = self.repo.get_dashboard_counts()
        top_items = data.pop("top_unanswered_questions", [])
        data["top_unanswered_questions"] = [
            {
                "id": item.id,
                "summary": item.summary or item.question or "",
                "frequency": item.frequency,
                "status": item.status,
                "last_seen_time": item.last_seen_time,
            }
            for item in top_items
        ]
        data["top_negative_feedback_questions"] = data.get("top_negative_feedback_questions", [])
        return data
