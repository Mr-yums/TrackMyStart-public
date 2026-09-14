"""[OXIO] Rabatteurs + agrégats de rabatage (clients amenés, commission due)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from yumnews.domain.models import Affiliate, Redemption
from yumnews.repositories.base import Repository


@dataclass(frozen=True)
class AffiliateReport:
    affiliate: Affiliate
    paid_redemptions: int  # nombre de paiements amenés (= mois payés via ses codes)
    distinct_clients: int  # clients uniques amenés
    revenue_cents: int  # chiffre amené (somme des montants payés)
    commission_cents: (
        int  # commission totale due au rabatteur (figée à chaque paiement)
    )


class AffiliateRepository(Repository[Affiliate]):
    model = Affiliate

    def all_active(self) -> list[Affiliate]:
        return list(
            self.session.scalars(select(Affiliate).where(Affiliate.is_active.is_(True)))
        )

    def report(self, affiliate_id: int) -> AffiliateReport | None:
        affiliate = self.get(affiliate_id)
        if affiliate is None:
            return None
        stmt = select(
            func.count(Redemption.id),
            func.count(func.distinct(Redemption.user_id)),
            func.coalesce(func.sum(Redemption.amount_cents), 0),
            func.coalesce(func.sum(Redemption.commission_cents), 0),
        ).where(Redemption.affiliate_id == affiliate_id)
        paid, clients, revenue, commission = self.session.execute(stmt).one()
        return AffiliateReport(
            affiliate=affiliate,
            paid_redemptions=int(paid or 0),
            distinct_clients=int(clients or 0),
            revenue_cents=int(revenue or 0),
            commission_cents=int(commission or 0),
        )
