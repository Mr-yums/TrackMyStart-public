from __future__ import annotations

from sqlalchemy.orm import Session
from config import InvoiceIssuer
from decimal import Decimal, ROUND_HALF_UP

from yumnews.domain.models import Invoice, Payment, utcnow
from yumnews.repositories import InvoiceRepository

VAT_RATE_PERCENT = 20


class InvoiceService:
    prefix = "YN"

    def __init__(self, issuer: InvoiceIssuer | None = None):
        # [Sol] Le taux configurable est figé dans chaque facture à son émission.
        self.issuer = issuer or InvoiceIssuer()
        if not 0 <= self.issuer.vat_rate_percent <= 100:
            raise ValueError("Taux de TVA hors limites.")

    def issue(self, session: Session, payment: Payment) -> Invoice:
        repo = InvoiceRepository(session)
        now = utcnow()
        number = repo.next_number(now.year)
        ttc = payment.amount_cents
        ht = int(
            (Decimal(ttc) * 100 / (100 + self.issuer.vat_rate_percent)).quantize(
                Decimal(1), rounding=ROUND_HALF_UP
            )
        )
        invoice = Invoice(
            number=f"{self.prefix}-{now.year}-{number:06d}",
            user_id=payment.user_id,
            payment_id=payment.id,
            description=payment.description,
            amount_ht_cents=ht,
            vat_cents=ttc - ht,
            amount_ttc_cents=ttc,
            currency=payment.currency,
            issued_at=now,
        )
        invoice = repo.add(invoice)
        from dataclasses import asdict

        repo.save_snapshot(
            invoice.id,
            {
                "issuer": asdict(self.issuer),
                "customer_name": payment.user.display_name,
                "customer_email": payment.user.email,
            },
        )
        return invoice
