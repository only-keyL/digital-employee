"""知识投稿仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.base_repository import BaseRepository


class KnowledgeContributionRepository(BaseRepository[KnowledgeContribution]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeContribution)

    def get_by_contribution_id(self, contribution_id: str) -> KnowledgeContribution | None:
        stmt = select(KnowledgeContribution).where(
            KnowledgeContribution.contribution_id == contribution_id
        )
        return self.session.scalar(stmt)

    def create(self, record: KnowledgeContribution) -> KnowledgeContribution:
        self.session.add(record)
        self.session.flush()
        return record

    def save(self) -> None:
        self.session.flush()
