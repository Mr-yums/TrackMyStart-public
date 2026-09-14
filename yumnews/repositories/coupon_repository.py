"""[OXIO] Accès aux coupons et à leurs utilisations (redemptions)."""

from __future__ import annotations

from sqlalchemy import func, select, update

from yumnews.domain.enums import CouponStatus, PaymentStatus
from yumnews.domain.models import Coupon, Payment, Redemption
from yumnews.repositories.base import Repository


class CouponRepository(Repository[Coupon]):
    model = Coupon

    @staticmethod
    def normalize(code: str) -> str:
        return (code or "").strip().upper()

    def by_code(self, code: str) -> Coupon | None:
        return self.session.scalar(
            select(Coupon).where(Coupon.code == self.normalize(code))
        )

    def active_by_code(self, code: str, *, reserve: bool = False) -> Coupon | None:
        # [Sol] Sérialiser validation + création du paiement dans la même transaction.
        if reserve and self.session.get_bind().dialect.name == "sqlite":
            self.session.execute(
                update(Coupon)
                .where(Coupon.code == self.normalize(code))
                .values(value=Coupon.value, updated_at=Coupon.updated_at),
                execution_options={"synchronize_session": False},
            )
        stmt = select(Coupon).where(
            Coupon.code == self.normalize(code),
            Coupon.status == CouponStatus.ACTIVE,
        )
        if reserve:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        return self.session.scalar(stmt)

    def reserved_count(self, coupon_id: int, user_id: int | None = None) -> int:
        # [Sol] Un checkout ouvert réserve sa place jusqu'au résultat définitif.
        stmt = (
            select(func.count())
            .select_from(Payment)
            .where(
                Payment.coupon_id == coupon_id,
                Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.SUCCEEDED]),
            )
        )
        if user_id is not None:
            stmt = stmt.where(Payment.user_id == user_id)
        return self.session.scalar(stmt) or 0

    def redemption_count(self, coupon_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Redemption)
            .where(Redemption.coupon_id == coupon_id)
        )
        return self.session.scalar(stmt) or 0

    def user_redemption_count(self, coupon_id: int, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Redemption)
            .where(Redemption.coupon_id == coupon_id, Redemption.user_id == user_id)
        )
        return self.session.scalar(stmt) or 0

    def add_redemption(self, redemption: Redemption) -> Redemption:
        self.session.add(redemption)
        self.session.flush()
        return redemption
