from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get_by_id(self, record_id: int) -> ModelT | None:
        return self.session.get(self.model, record_id)

    def count(self, stmt: Select | None = None) -> int:
        if stmt is None:
            stmt = select(func.count()).select_from(self.model)
        else:
            stmt = select(func.count()).select_from(stmt.subquery())
        return int(self.session.scalar(stmt) or 0)

    def list(
        self,
        *,
        offset: int = 0,
        limit: int = 50,
        stmt: Select | None = None,
    ) -> list[ModelT]:
        if stmt is None:
            stmt = select(self.model)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.session.scalars(stmt).all())
