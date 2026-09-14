"""Accès base de données : UN moteur SQLAlchemy par application, sessions scopées.

Leçon tirée de SearchMyJob : ne jamais créer un ``Engine`` dans chaque
service. Ici ``Database`` est instancié une fois dans le conteneur et fournit
un ``session_scope()`` qui commit ou rollback automatiquement.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from yumnews.domain.models import Base


class Database:
    def __init__(self, url: str, echo: bool = False) -> None:
        kwargs: dict = {"echo": echo, "pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs.update(pool_size=10, max_overflow=10, pool_recycle=1800)
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_fk)
        self._factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )
        self.session = scoped_session(self._factory)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Unité de travail : commit si tout va bien, rollback sinon."""
        session = self.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def remove(self) -> None:
        self.session.remove()


def _enable_sqlite_fk(dbapi_connection, _record) -> None:  # pragma: no cover - trivial
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
