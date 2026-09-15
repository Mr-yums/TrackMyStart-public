"""Coupons de réduction et rabatteurs.

Deux usages couverts par un seul moteur :
- **Code rabatteur** : coupon ``FIXED`` à 1200 (→ 12 €), rattaché à un ``Affiliate``, sans limite
  par client (12 € à chaque mois payé). Chaque paiement réussi génère une commission figée
  (% de ce qui reste après l'URSSAF) et, au premier paiement du client, une passphrase Discord.
- **Promo découverte** : coupon ``PERCENT`` à 20 %, sans rabatteur, plafonné à 5 paiements par
  compte (``max_periods_per_user=5``) → 5 premiers mois à -20 %.

Le prix de base vient toujours du serveur ; le coupon ne fait que réduire ``Payment.amount_cents``.
La redemption (et la commission) n'est enregistrée qu'au paiement **réussi** (``redeem`` depuis
``BillingService._finalize``) : une carte refusée ne consomme pas de mois de promo ni de commission.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from yumnews.domain.enums import CouponKind
from yumnews.domain.models import Coupon, Payment, Redemption, User, utcnow
from yumnews.repositories import CouponRepository
from yumnews.services.errors import CouponError
from yumnews.services.passphrase_service import PassphraseService


@dataclass(frozen=True)
class CouponQuote:
    """Résultat d'une validation de code : le coupon et le prix qui en découle."""

    coupon: Coupon
    base_cents: int
    amount_cents: int
    discount_cents: int


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


class CouponService:
    def __init__(
        self, urssaf_rate_percent: int, passphrases: PassphraseService
    ) -> None:
        if not 0 <= urssaf_rate_percent <= 100:
            raise ValueError("Taux URSSAF hors limites.")
        self.urssaf_rate_percent = urssaf_rate_percent
        self.passphrases = passphrases

    # ---- validation / prix ------------------------------------------
    def quote(
        self,
        session: Session,
        user: User,
        code: str,
        base_cents: int,
        *,
        reserve: bool = False,
    ) -> CouponQuote:
        """Valide un code pour ce client et renvoie le prix réduit. Lève ``CouponError`` sinon."""
        repo = CouponRepository(session)
        coupon = repo.active_by_code(code, reserve=reserve)
        if coupon is None:
            raise CouponError("Code promo invalide.", code="coupon_invalid")
        if coupon.expires_at is not None and coupon.expires_at <= utcnow():
            raise CouponError("Code promo expiré.", code="coupon_expired")
        if (
            coupon.max_redemptions is not None
            and repo.reserved_count(coupon.id) >= coupon.max_redemptions
        ):
            raise CouponError("Code promo épuisé.", code="coupon_exhausted")
        if (
            coupon.max_periods_per_user is not None
            and repo.reserved_count(coupon.id, user.id) >= coupon.max_periods_per_user
        ):
            raise CouponError(
                "Offre déjà utilisée au maximum sur ce compte.", code="coupon_exhausted"
            )
        amount = self._amount_for(coupon, base_cents)
        return CouponQuote(
            coupon=coupon,
            base_cents=base_cents,
            amount_cents=amount,
            discount_cents=base_cents - amount,
        )

    def _amount_for(self, coupon: Coupon, base_cents: int) -> int:
        if coupon.kind == CouponKind.FIXED:
            return max(
                0, min(coupon.value, base_cents)
            )  # prix fixe, jamais au-dessus du tarif de base
        discount = _round(Decimal(base_cents) * coupon.value / 100)
        return max(0, base_cents - discount)

    # ---- redemption (paiement réussi) -------------------------------
    def redeem(self, session: Session, payment: Payment) -> Redemption | None:
        """Enregistre l'utilisation d'un coupon après un paiement réussi (commission figée)."""
        if payment.coupon_id is None:
            return None
        repo = CouponRepository(session)
        coupon = repo.get(payment.coupon_id)
        if coupon is None:
            return None
        commission = 0
        urssaf = 0
        if coupon.affiliate_id is not None and coupon.affiliate is not None:
            urssaf = self.urssaf_rate_percent
            net = Decimal(payment.amount_cents) * (100 - urssaf) / 100
            commission = _round(net * coupon.affiliate.commission_percent / 100)
        redemption = repo.add_redemption(
            Redemption(
                coupon_id=coupon.id,
                affiliate_id=coupon.affiliate_id,
                user_id=payment.user_id,
                payment_id=payment.id,
                amount_cents=payment.amount_cents,
                discount_cents=payment.discount_cents or 0,
                urssaf_rate_percent=urssaf,
                commission_cents=commission,
            )
        )
        if coupon.affiliate_id is not None:
            self.passphrases.issue_for(
                session, payment.user, coupon.affiliate_id, redemption
            )
        return redemption
