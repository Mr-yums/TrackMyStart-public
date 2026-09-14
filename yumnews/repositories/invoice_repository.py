from __future__ import annotations

from sqlalchemy import select

from yumnews.domain.models import Invoice, InvoiceCounter, InvoiceSnapshot
from yumnews.repositories.base import Repository


class InvoiceRepository(Repository[Invoice]):
    model = Invoice

    def for_user(self, user_id: int) -> list[Invoice]:
        stmt = (
            select(Invoice)
            .where(Invoice.user_id == user_id)
            .order_by(Invoice.id.desc())
        )
        return list(self.session.scalars(stmt))

    def by_number_for_user(self, number: str, user_id: int) -> Invoice | None:
        stmt = select(Invoice).where(
            Invoice.number == number, Invoice.user_id == user_id
        )
        return self.session.scalar(stmt)

    def save_snapshot(self, invoice_id: int, details: dict) -> None:
        """[Sol] Émetteur et client conservés au moment du paiement."""
        self.session.add(InvoiceSnapshot(invoice_id=invoice_id, details=details))
        self.session.flush()

    def snapshot(self, invoice_id: int) -> dict | None:
        row = self.session.get(InvoiceSnapshot, invoice_id)
        return row.details if row else None

    def next_number(self, year: int) -> int:
        """Numérotation continue par année, ligne verrouillée le temps de la transaction."""
        stmt = select(InvoiceCounter).where(InvoiceCounter.year == year)
        if self.session.bind is not None and self.session.bind.dialect.name != "sqlite":
            stmt = stmt.with_for_update()
        counter = self.session.scalar(stmt)
        if counter is None:
            counter = InvoiceCounter(year=year, last_number=0)
            self.session.add(counter)
            self.session.flush()
        counter.last_number += 1
        self.session.flush()
        return counter.last_number
