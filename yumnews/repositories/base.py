"""Repository générique : toutes les requêtes SQL passent par une sous-classe."""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from yumnews.domain.models import Base

T = TypeVar("T", bound=Base)


class Repository(Generic[T]):
    model: type[T]

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, id_: int) -> T | None:
        return self.session.get(self.model, id_)

    def add(self, entity: T) -> T:
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: T) -> None:
        self.session.delete(entity)
        self.session.flush()

    def all(self) -> list[T]:
        return list(self.session.scalars(select(self.model)))
