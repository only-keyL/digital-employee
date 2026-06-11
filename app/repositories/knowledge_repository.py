from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_card import KnowledgeCard
from app.repositories.base_repository import BaseRepository


class KnowledgeRepository(BaseRepository[KnowledgeCard]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeCard)

    def get_by_id(self, card_id: int) -> KnowledgeCard | None:
        stmt = select(KnowledgeCard).where(KnowledgeCard.id == card_id)
        return self.session.scalars(stmt).first()

    def get_active_by_id(self, card_id: int) -> KnowledgeCard | None:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.deleted == 0,
        )
        return self.session.scalars(stmt).first()

    def get_searchable_by_id(self, card_id: int) -> KnowledgeCard | None:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
            KnowledgeCard.enabled == 1,
        )
        return self.session.scalars(stmt).first()

    def list_approved_enabled(self) -> list[KnowledgeCard]:
        stmt = (
            select(KnowledgeCard)
            .where(
                KnowledgeCard.deleted == 0,
                KnowledgeCard.audit_status == "approved",
                KnowledgeCard.enabled == 1,
            )
            .order_by(KnowledgeCard.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def count_vector_synced(self) -> int:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
            KnowledgeCard.enabled == 1,
            KnowledgeCard.vector_status == "synced",
        )
        return self.count(stmt)

    def get_by_title(self, title: str) -> KnowledgeCard | None:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.title == title,
            KnowledgeCard.deleted == 0,
        )
        return self.session.scalars(stmt).first()

    def find_login_permission_card(self) -> KnowledgeCard | None:
        preferred_title = "登录失败提示账号无权限处理办法"
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
            KnowledgeCard.enabled == 1,
            KnowledgeCard.title == preferred_title,
        )
        card = self.session.scalars(stmt).first()
        if card is not None:
            return card

        fallback_stmt = (
            select(KnowledgeCard)
            .where(
                KnowledgeCard.deleted == 0,
                KnowledgeCard.audit_status == "approved",
                KnowledgeCard.enabled == 1,
                KnowledgeCard.module_name == "登录权限",
            )
            .order_by(KnowledgeCard.id.asc())
            .limit(1)
        )
        return self.session.scalars(fallback_stmt).first()

    def list_cards(self, *, offset: int = 0, limit: int = 50) -> list[KnowledgeCard]:
        stmt = (
            select(KnowledgeCard)
            .where(KnowledgeCard.deleted == 0)
            .order_by(KnowledgeCard.update_time.desc())
        )
        return self.list(offset=offset, limit=limit, stmt=stmt)

    def count_cards(self) -> int:
        stmt = select(KnowledgeCard).where(KnowledgeCard.deleted == 0)
        return self.count(stmt)

    def count_approved_enabled(self) -> int:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
            KnowledgeCard.enabled == 1,
        )
        return self.count(stmt)

    def count_approved(self) -> int:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
        )
        return self.count(stmt)

    def count_pending_audit(self) -> int:
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "pending",
        )
        return self.count(stmt)

    def add(self, card: KnowledgeCard) -> KnowledgeCard:
        self.session.add(card)
        self.session.flush()
        return card

    def save(self) -> None:
        self.session.commit()

    def refresh(self, card: KnowledgeCard) -> KnowledgeCard:
        self.session.refresh(card)
        return card
