"""[Sol] La liste d’attente ne crée ni paiement ni droit Premium."""

import re
from unittest.mock import Mock

import pytest
from sqlalchemy import select, func

from config import Settings
from yumnews.domain.models import Payment, User, UserPreferences, Subscription
from yumnews.services.errors import PaymentError
from yumnews.services.preregistration import PreregistrationService


def close_payments(container):
    object.__setattr__(container.settings, "payments_enabled", False)
    container.billing.payments_enabled = False


def test_closed_by_default(monkeypatch):
    monkeypatch.delenv("PAYMENTS_ENABLED", raising=False)
    assert Settings().payments_enabled is False
    assert Settings.from_env().payments_enabled is False


def test_public_checkout_becomes_waitlist(client, container):
    close_payments(container)
    assert client.get("/abonnement").location.endswith("/preinscription")
    for path in ["/preinscription", "/tarifs"]:
        response = client.get(path)
        assert response.status_code == 200
        assert "Aucune carte" in response.text
        assert "Créer mon compte gratuit" in response.text
        assert "squarecdn" not in response.text
    assert (
        "/connexion"
        in client.post(
            "/preinscription", data={"action": "join", "consent": "yes"}
        ).location
    )


@pytest.mark.parametrize(
    "path",
    [
        "/abonnement/carte",
        "/abonnement/devis",
        "/abonnement/hosted/nowpayments",
        "/abonnement/hebergé/nowpayments",
    ],
)
def test_payment_routes_closed_with_valid_csrf(path, logged_client, app, container):
    close_payments(container)
    app.config["WTF_CSRF_ENABLED"] = True
    token = re.search(
        r'name="csrf_token" value="([^"]+)"', logged_client.get("/preinscription").text
    )[1]
    container.billing.pay_with_card = Mock(side_effect=AssertionError("Payment called"))
    container.billing.start_hosted_checkout = Mock(
        side_effect=AssertionError("Checkout called")
    )
    response = logged_client.post(
        path,
        json={"token": "fake", "expected_amount_cents": 2000},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 503
    assert response.json["code"] == "payments_closed"
    with container.db.session_scope() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_direct_billing_also_closed(container, user):
    close_payments(container)
    with container.db.session_scope() as session:
        account = session.get(User, user)
        for call in [
            lambda: container.billing.pay_with_card(session, account, "fake"),
            lambda: container.billing.start_hosted_checkout(
                session, account, "nowpayments"
            ),
        ]:
            with pytest.raises(PaymentError) as exc:
                call()
            assert exc.value.code == "payments_closed"
        assert session.scalar(select(func.count()).select_from(Payment)) == 0


def test_explicit_reversible_idempotent_consent(logged_client, container, user):
    close_payments(container)
    service = PreregistrationService()
    with container.db.session_scope() as session:
        session.add(UserPreferences(user_id=user, settings={"keep_me": {"actor": 42}}))
        before_subs = session.scalar(select(func.count()).select_from(Subscription))
    sent = len(container.mailer.sent)
    logged_client.post("/preinscription", data={"action": "join"})
    with container.db.session_scope() as session:
        assert not service.status(session, user)
    for _ in range(2):
        response = logged_client.post(
            "/preinscription",
            data={"action": "join", "consent": "yes", "user_id": "999"},
            follow_redirects=True,
        )
        assert "Vous êtes sur la liste" in response.text
        with container.db.session_scope() as session:
            state = service.status(session, user)
            assert state["active"] and state["consent"]
            if _ == 0:
                original = state
            else:
                assert original == state
            assert session.get(UserPreferences, user).settings["keep_me"] == {
                "actor": 42
            }
            assert (
                session.scalar(select(func.count()).select_from(Subscription))
                == before_subs
            )
            assert session.scalar(select(func.count()).select_from(Payment)) == 0
    assert len(container.mailer.sent) == sent
    logged_client.post("/preinscription", data={"action": "leave"})
    with container.db.session_scope() as session:
        assert service.status(session, user)["active"] is False


def test_csrf_required(logged_client, app, container, user):
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.post(
            "/preinscription", data={"action": "join", "consent": "yes"}
        ).status_code
        == 400
    )
    with container.db.session_scope() as session:
        assert not PreregistrationService().status(session, user)


def test_login_returns_to_waitlist(client, user):
    response = client.post(
        "/connexion?next=/preinscription",
        data={"email": "yums@example.com", "password": "motdepasse123"},
    )
    assert response.location.endswith("/preinscription")
    response = client.get("/connexion?next=https://example.org")
    assert "example.org" not in response.location


def test_admin_count_excludes_withdrawals(app, container, user):
    service = PreregistrationService()
    with container.db.session_scope() as session:
        service.set_status(session, user, True)
    runner = app.test_cli_runner()
    result = runner.invoke(args=["preregistrations"])
    assert result.exit_code == 0
    assert '"active": 1' in result.output
    assert "yums@example.com" not in result.output
    with container.db.session_scope() as session:
        service.set_status(session, user, False)
    assert '"active": 0' in runner.invoke(args=["preregistrations"]).output


def test_new_account_returns_without_automatic_optin(client, container):
    response = client.post(
        "/inscription?next=/preinscription",
        data={
            "display_name": "Test attente",
            "email": "attente@example.com",
            "password": "motdepasse123",
            "confirm": "motdepasse123",
            "terms": "y",
        },
    )
    assert response.location.endswith("/preinscription")
    with container.db.session_scope() as session:
        account = session.scalar(
            select(User).where(User.email == "attente@example.com")
        )
        assert account is not None
        assert not PreregistrationService().status(session, account.id)
    assert "Me préinscrire gratuitement" in client.get("/preinscription").text
