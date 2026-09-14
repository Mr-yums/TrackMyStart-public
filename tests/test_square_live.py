"""[Sol] Paiements réels dans Sandbox uniquement, base et emails de test isolés."""

import pytest
from config import Settings
from yumnews.payments.square_gateway import SquareGateway
from yumnews.payments.gateway import ChargeRequest
from yumnews.repositories import UserRepository, InvoiceRepository
from yumnews.domain.enums import PaymentStatus


@pytest.mark.live
def test_square_sandbox_payment_invoice_decline_and_idempotence(container, user):
    settings = Settings.from_env().square
    assert settings.environment == "sandbox", "Ce test refuse la production"
    assert settings.enabled, "Clés Square Sandbox incomplètes"
    gateway = SquareGateway(settings)
    from yumnews.payments.registry import GatewayRegistry

    container.billing.gateways = GatewayRegistry([gateway])
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        success = container.billing.pay_with_card(session, entity, "cnon:card-nonce-ok")
        assert success.status == PaymentStatus.SUCCEEDED
        invoice = InvoiceRepository(session).for_user(user)[0]
        assert invoice.amount_ttc_cents == 2000 and invoice.payment_id == success.id
        assert container.subscriptions.current(session, user) is not None
        retry = gateway.charge(
            ChargeRequest(
                order_id=success.order_id,
                amount_cents=success.amount_cents,
                currency=success.currency,
                description=success.description,
                customer_email=entity.email,
                source_token="cnon:card-nonce-ok",
            )
        )
        assert (
            retry.succeeded and retry.provider_payment_id == success.provider_payment_id
        )
        declined = container.billing.pay_with_card(
            session, entity, "cnon:card-nonce-declined"
        )
        assert declined.status == PaymentStatus.FAILED
        assert len(InvoiceRepository(session).for_user(user)) == 1
