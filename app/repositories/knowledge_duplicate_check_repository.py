"""知识重复检测记录数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_duplicate_check_log import KnowledgeDuplicateCheckLog
from app.repositories.base_repository import BaseRepository


class KnowledgeDuplicateCheckRepository(BaseRepository[KnowledgeDuplicateCheckLog]):
    """knowledge_duplicate_check_log 表基础查询与持久化。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeDuplicateCheckLog)

    def create(self, record: KnowledgeDuplicateCheckLog) -> KnowledgeDuplicateCheckLog:
        """创建重复检测记录。"""
        self.session.add(record)
        self.session.flush()
        return record

    def list_recent(self, *, offset: int = 0, limit: int = 50) -> list[KnowledgeDuplicateCheckLog]:
        """按创建时间倒序查询最近的重复检测记录。"""
        stmt = select(KnowledgeDuplicateCheckLog).order_by(
            KnowledgeDuplicateCheckLog.created_at.desc()
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def list_by_source_card_id(
        self,
        source_card_id: int,
        *,
        limit: int = 50,
    ) -> list[KnowledgeDuplicateCheckLog]:
        """查询指定源卡片的重复检测记录。"""
        stmt = (
            select(KnowledgeDuplicateCheckLog)
            .where(KnowledgeDuplicateCheckLog.source_card_id == source_card_id)
            .order_by(KnowledgeDuplicateCheckLog.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def count_by_check_level(self, check_level: str) -> int:
        """统计指定重复等级的检测记录数量。"""
        stmt = select(KnowledgeDuplicateCheckLog).where(
            KnowledgeDuplicateCheckLog.check_level == check_level
        )
        return self.count(stmt)

    def save(self) -> None:
        """提交当前事务。"""
        self.session.commit()
