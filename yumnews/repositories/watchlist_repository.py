from __future__ import annotations

from sqlalchemy import func, select

from yumnews.domain.models import WatchlistItem
from yumnews.repositories.base import Repository


class WatchlistRepository(Repository[WatchlistItem]):
    model = WatchlistItem

    def for_user(self, user_id: int) -> list[WatchlistItem]:
        stmt = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc())
        )
        return list(self.session.scalars(stmt))

    def find(
        self, user_id: int, media_type: str, media_id: str
    ) -> WatchlistItem | None:
        stmt = select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.media_type == media_type,
            WatchlistItem.media_id == str(media_id),
        )
        return self.session.scalar(stmt)

    def count_for_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
        )
        return self.session.scalar(stmt) or 0
