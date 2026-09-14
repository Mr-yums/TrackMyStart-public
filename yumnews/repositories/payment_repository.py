from __future__ import annotations

from sqlalchemy import select, update

from yumnews.domain.models import Payment
from yumnews.repositories.base import Repository


class PaymentRepository(Repository[Payment]):
    model = Payment

    def by_order_id(self, order_id: str, *, for_update: bool = False) -> Payment | None:
        # [Sol] Un seul webhook finalise une commande à la fois.
        if for_update and self.session.get_bind().dialect.name == "sqlite":
            self.session.execute(
                update(Payment)
                .where(Payment.order_id == order_id)
                .values(status=Payment.status, updated_at=Payment.updated_at),
                execution_options={"synchronize_session": False},
            )
        stmt = select(Payment).where(Payment.order_id == order_id)
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(stmt)

    def by_provider_payment_id(
        self, provider: str, provider_payment_id: str
    ) -> Payment | None:
        stmt = select(Payment).where(
            Payment.provider == provider,
            Payment.provider_payment_id == provider_payment_id,
        )
        return self.session.scalar(stmt)

    def for_user(self, user_id: int) -> list[Payment]:
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(Payment.id.desc())
        )
        return list(self.session.scalars(stmt))
