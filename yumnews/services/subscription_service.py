from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from yumnews.domain.enums import Plan, SubscriptionStatus
from yumnews.domain.models import Payment, Subscription, User, utcnow
from yumnews.repositories import SubscriptionRepository, UserRepository
from yumnews.services.access_policy import AccessPolicy, AccessPolicyFactory


class SubscriptionService:
    def __init__(self, period_days: int) -> None:
        self.period_days = period_days

    def current(self, session: Session, user_id: int) -> Subscription | None:
        return SubscriptionRepository(session).current_for_user(user_id)

    def plan_for(self, session: Session, user: User | None) -> Plan | None:
        if user is None:
            return None
        return Plan.PREMIUM if self.current(session, user.id) else Plan.FREE

    def policy_for(self, session: Session, user: User | None) -> AccessPolicy:
        return AccessPolicyFactory.for_plan(self.plan_for(session, user))

    def activate(
        self, session: Session, user: User, payment: Payment | None = None
    ) -> Subscription:
        """Nouvelle période. Si une période est encore en cours, on l'enchaîne (pas de perte)."""
        UserRepository(session).lock(
            user.id
        )  # [Sol] Enchaîner aussi deux activations simultanées.
        repo = SubscriptionRepository(session)
        now = utcnow()
        current = repo.current_for_user(user.id, now)
        start = current.current_period_end if current else now
        subscription = Subscription(
            user_id=user.id,
            plan=Plan.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
            started_at=start,
            current_period_end=start + timedelta(days=self.period_days),
            payment_id=payment.id if payment else None,
        )
        return repo.add(subscription)

    def expire_overdue(self, session: Session) -> int:
        return SubscriptionRepository(session).expire_overdue()

    def summary(self, session: Session, user: User) -> dict:
        current = self.current(session, user.id)
        latest = SubscriptionRepository(session).latest_for_user(user.id)
        return {
            "plan": (Plan.PREMIUM if current else Plan.FREE).value,
            "active": current is not None,
            "period_end": current.current_period_end.isoformat() if current else None,
            "days_left": max(0, (current.current_period_end - utcnow()).days)
            if current
            else 0,
            "last_status": latest.status.value
            if latest and hasattr(latest.status, "value")
            else (latest.status if latest else None),
        }
