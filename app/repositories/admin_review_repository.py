"""后台审核数据访问层：投稿与待审核知识查询（不含业务判断）。"""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.knowledge_card import KnowledgeCard
from app.models.knowledge_contribution import KnowledgeContribution
from app.repositories.base_repository import BaseRepository


class AdminReviewRepository:
    """knowledge_contribution / knowledge_card 的后台审核查询与状态更新。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._contrib_repo = BaseRepository(session, KnowledgeContribution)
        self._card_repo = BaseRepository(session, KnowledgeCard)

    def list_contributions(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        status: str | None = None,
        risk_level: str | None = None,
        duplicate_suspected: bool | None = None,
    ) -> list[KnowledgeContribution]:
        """分页查询投稿，默认按 created_at 倒序。"""
        stmt = select(KnowledgeContribution).order_by(desc(KnowledgeContribution.created_at))
        if status:
            stmt = stmt.where(KnowledgeContribution.status == status)
        if risk_level:
            stmt = stmt.where(KnowledgeContribution.risk_level == risk_level)
        if duplicate_suspected is not None:
            stmt = stmt.where(KnowledgeContribution.duplicate_suspected == duplicate_suspected)
        return self._contrib_repo.list(offset=offset, limit=limit, stmt=stmt)

    def count_contributions(
        self,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        duplicate_suspected: bool | None = None,
    ) -> int:
        stmt = select(KnowledgeContribution)
        if status:
            stmt = stmt.where(KnowledgeContribution.status == status)
        if risk_level:
            stmt = stmt.where(KnowledgeContribution.risk_level == risk_level)
        if duplicate_suspected is not None:
            stmt = stmt.where(KnowledgeContribution.duplicate_suspected == duplicate_suspected)
        return self._contrib_repo.count(stmt)

    def get_contribution_by_contribution_id(self, contribution_id: str) -> KnowledgeContribution | None:
        stmt = select(KnowledgeContribution).where(
            KnowledgeContribution.contribution_id == contribution_id
        )
        return self.session.scalar(stmt)

    def get_contribution_by_knowledge_card_id(self, knowledge_card_id: int) -> KnowledgeContribution | None:
        stmt = (
            select(KnowledgeContribution)
            .where(KnowledgeContribution.knowledge_card_id == knowledge_card_id)
            .order_by(desc(KnowledgeContribution.created_at))
            .limit(1)
        )
        return self.session.scalar(stmt)

    def list_pending_knowledge(self, *, offset: int = 0, limit: int = 20) -> list[KnowledgeCard]:
        """查询 audit_status=pending 且未删除的知识卡片。"""
        stmt = (
            select(KnowledgeCard)
            .where(
                KnowledgeCard.deleted == 0,
                KnowledgeCard.audit_status == "pending",
            )
            .order_by(desc(KnowledgeCard.create_time))
        )
        return self._card_repo.list(offset=offset, limit=limit, stmt=stmt)

    def count_pending_knowledge(self) -> int:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "pending",
        )
        return self._card_repo.count(stmt)

    def get_knowledge_by_id(self, knowledge_id: int) -> KnowledgeCard | None:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.id == knowledge_id,
            KnowledgeCard.deleted == 0,
        )
        return self.session.scalar(stmt)

    def update_contribution(self, record: KnowledgeContribution) -> KnowledgeContribution:
        self.session.flush()
        return record

    def update_knowledge_card(self, card: KnowledgeCard) -> KnowledgeCard:
        self.session.flush()
        return card

    def save(self) -> None:
        self.session.commit()

    def refresh(self, record: KnowledgeCard | KnowledgeContribution) -> None:
        self.session.refresh(record)
