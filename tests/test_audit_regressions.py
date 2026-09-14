"""[Sol] Régressions découvertes pendant l'audit avant publication."""

import json
from dataclasses import replace
import pytest
from yumnews.domain.models import User, Payment, Subscription, Invoice
from sqlalchemy import select, func
from yumnews.web.context import client_ip


def test_old_payment_notification_still_works_after_closure(client, container, user):
    with container.db.session_scope() as session:
        payment, _ = container.billing.start_hosted_checkout(
            session, session.get(User, user), "nowpayments"
        )
        order = payment.order_id
    container.billing.payments_enabled = False
    body = json.dumps({"order_id": order, "status": "finished"})
    assert (
        client.post(
            "/webhooks/nowpayments", data=body, headers={"x-nowpayments-sig": "bad"}
        ).status_code
        == 400
    )
    for _ in range(2):
        response = client.post(
            "/webhooks/nowpayments", data=body, headers={"x-nowpayments-sig": "good"}
        )
        assert response.status_code == 200
    with container.db.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Subscription)) == 1
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1


@pytest.mark.parametrize(
    "target", ["/\\example.org", "//example.org", "///example.org", "/\n/example.org"]
)
def test_login_rejects_ambiguous_redirects(logged_client, target):
    response = logged_client.get("/connexion", query_string={"next": target})
    assert response.location == "/app"


def test_untrusted_forwarded_ip_is_ignored(app):
    with app.test_request_context(
        "/",
        headers={"X-Forwarded-For": "1.2.3.4"},
        environ_base={"REMOTE_ADDR": "10.1.2.3"},
    ):
        assert client_ip() == "10.1.2.3"


def test_all_member_responses_are_private(logged_client):
    for path in [
        "/api/me",
        "/api/me/follows",
        "/api/me/watchlist",
        "/api/me/preferences",
    ]:
        r = logged_client.get(path)
        assert r.status_code == 200
        assert r.headers.get("Cache-Control") == "private, no-store"


def test_reset_revokes_existing_browser_session(logged_client, container, user):
    assert logged_client.get("/api/me").status_code == 200
    with container.db.session_scope() as session:
        container.auth.request_password_reset(session, "yums@example.com")
    token = container.mailer.sent[-1].text.split("/reinitialiser/")[1].split()[0]
    with container.db.session_scope() as session:
        container.auth.reset_password(session, token, "new-safe-password")
    assert logged_client.get("/api/me").status_code == 401


def test_mail_simulation_does_not_log_reset_token(caplog):
    from yumnews.services.mailer import LoggingMailer, Email
    import logging

    with caplog.at_level(logging.INFO):
        LoggingMailer().send(
            Email("private@example.org", "Reset", "secret-reset-token")
        )
    assert "secret-reset-token" not in caplog.text
    assert "private@example.org" not in caplog.text


def test_crypto_requires_finished_and_matching_signed_amount(container, user):
    from config import NowPaymentsSettings
    from yumnews.payments.nowpayments_gateway import NowPaymentsGateway
    from yumnews.services.errors import PaymentError

    gateway = NowPaymentsGateway(
        NowPaymentsSettings(api_key="test", ipn_secret="test-signing-secret")
    )
    with container.db.session_scope() as session:
        payment, _ = container.billing.start_hosted_checkout(
            session, session.get(User, user), "nowpayments"
        )
        order = payment.order_id
    payload = {
        "order_id": order,
        "payment_id": "test-1",
        "payment_status": "confirmed",
        "price_amount": 20,
        "price_currency": "eur",
    }

    def parse():
        return gateway.parse_notification(
            json.dumps(payload).encode(), gateway.sign(payload)
        )

    assert parse().succeeded is False and parse().final is False
    payload["payment_status"] = "finished"
    fake = container.gateways.hosted("nowpayments")
    fake.parse_notification = gateway.parse_notification
    for amount, currency in [(1, "eur"), (20, "usd")]:
        payload.update(price_amount=amount, price_currency=currency)
        with container.db.session_scope() as session:
            with pytest.raises(PaymentError):
                container.billing.handle_hosted_notification(
                    session,
                    "nowpayments",
                    json.dumps(payload).encode(),
                    gateway.sign(payload),
                )
    payload.update(price_amount=20, price_currency="eur")
    with container.db.session_scope() as session:
        result = container.billing.handle_hosted_notification(
            session, "nowpayments", json.dumps(payload).encode(), gateway.sign(payload)
        )
        assert result.status.value == "succeeded"


def test_proxy_setting_uses_last_hop_only(settings):
    from yumnews import create_app

    application = create_app(replace(settings, trusted_proxy_hops=1))

    @application.get("/test-ip")
    def ip():
        return client_ip()

    r = application.test_client().get(
        "/test-ip", headers={"X-Forwarded-For": "spoofed, 192.0.2.40"}
    )
    assert r.text == "192.0.2.40"


def test_stale_password_reset_cannot_overwrite_first_reset(container, user):
    from sqlalchemy.orm import Session
    from yumnews.services.errors import ValidationError

    with Session(container.db.engine) as a, Session(container.db.engine) as b:
        ua = a.get(User, user)
        ub = b.get(User, user)
        token = container.tokens.issue(
            "reset-password", {"uid": user, "h": ua.password_hash[-16:]}
        )
        container.auth.reset_password(a, token, "first-new-password")
        a.commit()
        with pytest.raises(ValidationError):
            container.auth.reset_password(b, token, "second-new-password")
        b.rollback()
        assert container.auth.hasher.verify(
            "first-new-password", b.get(User, user).password_hash
        )
