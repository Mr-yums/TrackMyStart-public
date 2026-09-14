from __future__ import annotations

from sqlalchemy import func, select

from yumnews.domain.models import Follow
from yumnews.repositories.base import Repository


class FollowRepository(Repository[Follow]):
    model = Follow

    def for_user(self, user_id: int) -> list[Follow]:
        stmt = (
            select(Follow)
            .where(Follow.user_id == user_id)
            .order_by(Follow.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def find(self, user_id: int, person_id: int) -> Follow | None:
        stmt = select(Follow).where(
            Follow.user_id == user_id, Follow.person_id == person_id
        )
        return self.session.scalar(stmt)

    def count_for_user(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Follow).where(Follow.user_id == user_id)
        return self.session.scalar(stmt) or 0
