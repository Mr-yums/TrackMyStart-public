from __future__ import annotations

import pytest

from config import PremiumOffer, Settings
from yumnews import create_app
from yumnews.domain.enums import PaymentProvider
from yumnews.payments import (
    CardGateway,
    ChargeRequest,
    ChargeResult,
    GatewayRegistry,
    HostedCheckout,
    HostedGateway,
    HostedNotification,
)
from yumnews.services.mailer import LoggingMailer


class FakeCardGateway(CardGateway):
    provider = PaymentProvider.SQUARE
    label = "Carte (test)"

    def __init__(self) -> None:
        self.requests: list[ChargeRequest] = []

    def client_config(self) -> dict:
        return {"application_id": "app", "location_id": "loc", "sandbox": True}

    def charge(self, request: ChargeRequest) -> ChargeResult:
        self.requests.append(request)
        if request.source_token == "tok-declined":
            return ChargeResult(succeeded=False, error_message="Carte refusée.")
        return ChargeResult(
            succeeded=True,
            provider_payment_id=f"sq-{request.order_id[:8]}",
            receipt_url="https://sq/r",
            card_brand="VISA",
            card_last4="4242",
        )


class FakeHostedGateway(HostedGateway):
    provider = PaymentProvider.NOWPAYMENTS
    label = "Crypto (test)"

    def __init__(self):
        self.orders = {}

    def client_config(self) -> dict:
        return {}

    def create_checkout(self, request: ChargeRequest) -> HostedCheckout:
        self.orders[request.order_id] = request
        return HostedCheckout(
            provider_payment_id="np-1",
            redirect_url=f"https://np/pay/{request.order_id}",
        )

    def parse_notification(
        self, body: bytes, signature: str | None
    ) -> HostedNotification:
        import json

        from yumnews.services.errors import PaymentError

        if signature != "good":
            raise PaymentError("Signature IPN invalide.")
        data = json.loads(body)
        ok = data["status"] == "finished"
        order = self.orders[data["order_id"]]
        return HostedNotification(
            amount_cents=order.amount_cents,
            currency=order.currency,
            order_id=data["order_id"],
            provider_payment_id="np-1",
            succeeded=ok,
            final=ok or data["status"] == "failed",
            raw=data,
        )


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        env="testing",
        payments_enabled=True,  # [Sol] Les tests de paiement existants utilisent uniquement des passerelles factices.
        secret_key="test-secret",
        db_url=f"sqlite:///{tmp_path}/test.db",
        site_url="http://test.local",
        advertising_path=str(
            tmp_path / "advertising.json"
        ),  # [Sol] Isolation des campagnes de test.
        tmdb_api_key="",
        offer=PremiumOffer(price_cents=2000, period_days=30, currency="EUR"),
    )


@pytest.fixture()
def app(settings):
    from yumnews.container import Container

    mailer = LoggingMailer()
    gateways = GatewayRegistry([FakeCardGateway(), FakeHostedGateway()])
    application = create_app(settings)
    # Remplace le conteneur par un conteneur de test (passerelles factices, mails en mémoire).
    container = Container(settings, gateways=gateways, mailer=mailer)
    application.extensions["container"] = container
    application.config["WTF_CSRF_ENABLED"] = False
    application.config["TESTING"] = True
    container.db.create_all()
    yield application
    container.db.remove()


@pytest.fixture()
def container(app):
    return app.extensions["container"]


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def user(container):
    with container.db.session_scope() as session:
        u = container.auth.register(
            session, "yums@example.com", "motdepasse123", "Yums"
        )
        session.flush()
        uid = u.id
    return uid


@pytest.fixture()
def logged_client(client, user):
    client.post(
        "/connexion", data={"email": "yums@example.com", "password": "motdepasse123"}
    )
    return client


# [Sol] Les tests réseau restent une action explicite.
def pytest_addoption(parser):
    parser.addoption("--run-live", action="store_true", default=False)


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-live"):
        for item in items:
            if "live" in item.keywords:
                item.add_marker(
                    pytest.mark.skip(reason="Square Sandbox : utiliser --run-live")
                )
