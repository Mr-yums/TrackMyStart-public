from __future__ import annotations

from sqlalchemy import func, select, update

from yumnews.domain.models import User
from yumnews.repositories.base import Repository


class UserRepository(Repository[User]):
    model = User

    def by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return self.session.scalar(stmt)

    def count(self) -> int:
        return self.session.scalar(select(func.count()).select_from(User)) or 0

    def replace_password(self, user: User, expected: str, replacement: str) -> bool:
        """[Sol] Compare-et-échange : deux resets du même jeton ne peuvent réussir."""
        result = self.session.execute(
            update(User)
            .where(User.id == user.id, User.password_hash == expected)
            .values(password_hash=replacement)
            .execution_options(synchronize_session=False)
        )
        self.session.expire(user)
        return result.rowcount == 1

    def lock(self, user_id: int) -> None:
        """[Sol] Sérialiser quotas/périodes par compte, sur SQLite comme PostgreSQL."""
        self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(id=user_id)
            .execution_options(synchronize_session=False)
        )
