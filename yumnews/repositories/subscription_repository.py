from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from yumnews.domain.enums import SubscriptionStatus
from yumnews.domain.models import Subscription, utcnow
from yumnews.repositories.base import Repository


class SubscriptionRepository(Repository[Subscription]):
    model = Subscription

    def current_for_user(
        self, user_id: int, now: datetime | None = None
    ) -> Subscription | None:
        now = now or utcnow()
        stmt = (
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.current_period_end > now,
            )
            .order_by(Subscription.current_period_end.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def latest_for_user(self, user_id: int) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.id.desc())
            .limit(1)
        )
        return self.session.scalar(stmt)

    def history_for_user(self, user_id: int) -> list[Subscription]:
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.id.desc())
        )
        return list(self.session.scalars(stmt))

    def expire_overdue(self, now: datetime | None = None) -> int:
        """Un seul UPDATE ensembliste (au lieu du DELETE en boucle de SearchMyJob)."""
        now = now or utcnow()
        stmt = (
            update(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.current_period_end <= now,
            )
            .values(status=SubscriptionStatus.EXPIRED, updated_at=now)
        )
        result = self.session.execute(stmt)
        return result.rowcount or 0
