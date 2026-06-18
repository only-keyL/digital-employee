"""知识卡片数据访问层。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_card import KnowledgeCard
from app.repositories.base_repository import BaseRepository


class KnowledgeRepository(BaseRepository[KnowledgeCard]):
    """knowledge_card 表查询与持久化。"""

    def __init__(self, session: Session) -> None:
        super().__init__(session, KnowledgeCard)

    def get_by_id(self, card_id: int) -> KnowledgeCard | None:
        """按主键查询（含已删除）。"""
        stmt = select(KnowledgeCard).where(KnowledgeCard.id == card_id)
        return self.session.scalars(stmt).first()

    def get_active_by_id(self, card_id: int) -> KnowledgeCard | None:
        """按主键查询未软删除的卡片。"""
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.deleted == 0,
        )
        return self.session.scalars(stmt).first()

    def get_searchable_by_id(self, card_id: int) -> KnowledgeCard | None:
        """查询可参与 RAG 检索的卡片（已审核且启用）。"""
        stmt = select(KnowledgeCard).where(
            KnowledgeCard.id == card_id,
            KnowledgeCard.deleted == 0,
            KnowledgeCard.audit_status == "approved",
            KnowledgeCard.enabled == 1,
        )
        return self.session.scalars(stmt).first()

    def list_approved_enabled(self) -> list[KnowledgeCard]:
        """列出全部已审核且启用的卡片。"""
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
        """查找登录权限演示卡片（规则匹配遗留）。"""
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

    def list_duplicate_candidates(self, *, exclude_card_id: int | None = None) -> list[KnowledgeCard]:
        """查询可参与重复检测的候选知识卡片（approved / pending，未删除）。"""
        stmt = (
            select(KnowledgeCard)
            .where(
                KnowledgeCard.deleted == 0,
                KnowledgeCard.audit_status.in_(("approved", "pending")),
            )
            .order_by(KnowledgeCard.id.asc())
        )
        if exclude_card_id is not None:
            stmt = stmt.where(KnowledgeCard.id != exclude_card_id)
        return list(self.session.scalars(stmt).all())

    def get_duplicate_candidate_by_id(self, card_id: int) -> KnowledgeCard | None:
        """查询重复检测候选卡片详情（仅 approved / pending 且未删除）。"""
        card = self.get_active_by_id(card_id)
        if card is None:
            return None
        if card.audit_status not in {"approved", "pending"}:
            return None
        return card
