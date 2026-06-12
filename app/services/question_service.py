"""问答日志查询服务（管理后台页面用）。"""

from sqlalchemy.orm import Session

from app.repositories.question_repository import QuestionRepository


class QuestionService:
    """封装 question_log 的分页查询，供页面展示。"""

    def __init__(self, session: Session) -> None:
        self.repo = QuestionRepository(session)  # 问答日志仓储

    def list_for_page(self, *, page: int = 1, page_size: int = 20) -> dict:
        """分页查询问答日志，返回 items / total / page / page_size。"""
        offset = (page - 1) * page_size
        items = self.repo.list_logs(offset=offset, limit=page_size)
        total = self.repo.count_logs()
        return {
            "items": [
                {
                    "id": item.id,
                    "question_masked": item.question_masked or "",
                    "matched": item.matched,
                    "similarity_score": item.similarity_score,
                    "source_type": item.source_type or "",
                    "user_id": item.user_id or "",
                    "latency_ms": item.latency_ms,
                    "create_time": item.create_time,
                }
                for item in items
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
