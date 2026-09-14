"""[Sol] Montants, mentions figées et accès privé aux factures."""

from config import InvoiceIssuer
from yumnews.services.invoice_service import InvoiceService
from yumnews.repositories import InvoiceRepository, UserRepository


def test_invoice_uses_configured_rate_and_keeps_snapshot(container, user):
    container.billing.invoices = InvoiceService(
        InvoiceIssuer(name="Émetteur test", address="Adresse test", vat_rate_percent=0)
    )
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        container.billing.pay_with_card(session, entity, "tok-ok")
        invoice = InvoiceRepository(session).for_user(user)[0]
        assert (
            invoice.vat_cents == 0
            and invoice.amount_ht_cents == invoice.amount_ttc_cents == 2000
        )
        snapshot = InvoiceRepository(session).snapshot(invoice.id)
        assert snapshot["issuer"]["name"] == "Émetteur test"
        entity.display_name = "Nouveau pseudo"
        session.flush()
        assert (
            InvoiceRepository(session).snapshot(invoice.id)["customer_name"] == "Yums"
        )


def test_paid_invoice_is_printable_and_private(logged_client, app, container, user):
    assert (
        logged_client.post(
            "/abonnement/carte", json={"token": "tok-ok", "expected_amount_cents": 2000}
        ).status_code
        == 200
    )
    with container.db.session_scope() as session:
        invoice = InvoiceRepository(session).for_user(user)[0]
        path = "/compte/factures/" + invoice.number
        container.auth.register(
            session, "invoice-other@example.com", "another-test-password", "Other"
        )
    page = logged_client.get(path)
    assert (
        page.status_code == 200
        and b"Imprimer / PDF" in page.data
        and b"20.00" in page.data
    )
    other = app.test_client()
    assert other.get(path).status_code == 302
    other.post(
        "/connexion",
        data={
            "email": "invoice-other@example.com",
            "password": "another-test-password",
        },
    )
    assert other.get(path).status_code == 404
