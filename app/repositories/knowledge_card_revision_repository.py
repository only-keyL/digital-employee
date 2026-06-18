"""知识卡片修订建议数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_card_revision import KnowledgeCardRevision
from app.repositories.base_repository import BaseRepository


class KnowledgeCardRevisionRepository(BaseRepository[KnowledgeCardRevision]):
    """knowledge_card_revision 表基础查询与持久化。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeCardRevision)

    def create(self, record: KnowledgeCardRevision) -> KnowledgeCardRevision:
        """创建修订建议记录。"""
        self.session.add(record)
        self.session.flush()
        return record

    def get_by_id(self, revision_id: int) -> KnowledgeCardRevision | None:
        """按主键查询修订建议。"""
        return self.session.get(KnowledgeCardRevision, revision_id)

    def list_by_status(
        self,
        *,
        status: str,
        offset: int = 0,
        limit: int = 50,
    ) -> list[KnowledgeCardRevision]:
        """按修订状态分页查询。"""
        stmt = (
            select(KnowledgeCardRevision)
            .where(KnowledgeCardRevision.status == status)
            .order_by(KnowledgeCardRevision.created_at.desc())
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_by_status(self, status: str) -> int:
        """统计指定状态的修订建议数量。"""
        stmt = select(KnowledgeCardRevision).where(KnowledgeCardRevision.status == status)
        return self.count(stmt)

    def save(self) -> None:
        """提交当前事务。"""
        self.session.commit()
