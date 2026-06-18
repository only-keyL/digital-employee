from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only

from app.models.question_log import QuestionLog
from app.repositories.base_repository import BaseRepository


class QuestionRepository(BaseRepository[QuestionLog]):
    """问答日志（question_log）数据访问。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, QuestionLog)

    def list_logs(self, *, offset: int = 0, limit: int = 50) -> list[QuestionLog]:
        stmt = (
            select(QuestionLog)
            .options(
                load_only(
                    QuestionLog.id,
                    QuestionLog.request_id,
                    QuestionLog.question_masked,
                    QuestionLog.rewritten_question,
                    QuestionLog.user_id,
                    QuestionLog.group_id,
                    QuestionLog.source_type,
                    QuestionLog.intent,
                    QuestionLog.matched,
                    QuestionLog.similarity_score,
                    QuestionLog.primary_matched_card_id,
                    QuestionLog.primary_matched_card_title,
                    QuestionLog.confidence_level,
                    QuestionLog.answer_status,
                    QuestionLog.answer_source,
                    QuestionLog.system_name,
                    QuestionLog.module_name,
                    QuestionLog.used_context,
                    QuestionLog.context_source,
                    QuestionLog.answer,
                    QuestionLog.fallback_reason,
                    QuestionLog.need_human,
                    QuestionLog.risk_level,
                    QuestionLog.latency_ms,
                    QuestionLog.create_time,
                )
            )
            .order_by(QuestionLog.create_time.desc())
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_logs(self) -> int:
        return self.count()

    def count_matched(self) -> int:
        stmt = select(QuestionLog).where(QuestionLog.matched == 1)
        return self.count(stmt)

    def get_log_by_id(self, log_id: int) -> QuestionLog | None:
        return self.session.get(QuestionLog, log_id)

    def create_log(self, log: QuestionLog) -> QuestionLog:
        self.session.add(log)
        self.session.flush()
        return log

    def save(self) -> None:
        self.session.commit()

    def update_langsmith_trace_id(self, log_id: int, trace_id: str) -> None:
        """回写 LangSmith 追踪 ID 到指定问答日志。"""
        log = self.session.get(QuestionLog, log_id)
        if log is not None:
            log.langsmith_trace_id = trace_id
            self.session.flush()

    def list_user_recent_modules(
        self,
        *,
        user_id: str,
        group_id: str | None,
        days: int = 30,
        limit: int = 3,
    ) -> list[dict]:
        """查询用户近 N 天常问系统/模块，供后续上下文增强使用。"""
        since = datetime.now() - timedelta(days=days)
        stmt = (
            select(
                QuestionLog.system_name,
                QuestionLog.module_name,
                func.count(QuestionLog.id).label("ask_count"),
            )
            .where(
                QuestionLog.user_id == user_id,
                QuestionLog.create_time >= since,
                QuestionLog.system_name.isnot(None),
                QuestionLog.module_name.isnot(None),
            )
            .group_by(QuestionLog.system_name, QuestionLog.module_name)
            .order_by(func.count(QuestionLog.id).desc())
            .limit(limit)
        )
        if group_id:
            stmt = stmt.where(QuestionLog.group_id == group_id)

        rows = self.session.execute(stmt).all()
        return [
            {
                "system_name": row.system_name,
                "module_name": row.module_name,
                "ask_count": int(row.ask_count or 0),
            }
            for row in rows
        ]

    def update_trusted_answer_fields(
        self,
        log_id: int,
        *,
        primary_matched_card_id: int | None,
        primary_matched_card_title: str | None,
        confidence_level: str,
        answer_status: str,
        answer_source: str | None,
        system_name: str | None,
        module_name: str | None,
    ) -> None:
        """回填可信回答相关字段。"""
        log = self.session.get(QuestionLog, log_id)
        if log is None:
            return
        log.primary_matched_card_id = primary_matched_card_id
        log.primary_matched_card_title = primary_matched_card_title
        log.confidence_level = confidence_level
        log.answer_status = answer_status
        log.answer_source = answer_source
        log.system_name = system_name
        log.module_name = module_name
        self.session.flush()
