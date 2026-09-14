import json
from datetime import timedelta

from yumnews.domain.enums import PaymentStatus
from yumnews.repositories import InvoiceRepository, UserRepository


def test_card_payment_activates_premium_and_issues_invoice(container, user):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        assert container.subscriptions.plan_for(session, entity).value == "free"
        payment = container.billing.pay_with_card(session, entity, "tok-ok")
        assert payment.status == PaymentStatus.SUCCEEDED
        assert (
            payment.provider_payment_id.startswith("sq-")
            and payment.card_last4 == "4242"
        )
        assert container.subscriptions.plan_for(session, entity).value == "premium"
        invoice = InvoiceRepository(session).for_user(user)[0]
        assert invoice.number.startswith("YN-") and invoice.number.endswith("000001")
        assert (
            invoice.amount_ttc_cents == 2000
            and invoice.amount_ht_cents == 1667
            and invoice.vat_cents == 333
        )
    # Idempotence : la clé envoyée à la passerelle est l'order_id stable
    gw = container.gateways.card
    assert (
        gw.requests[-1].order_id == payment.order_id
        and gw.requests[-1].amount_cents == 2000
    )
    assert "Facture n° YN-" in container.mailer.sent[-1].text


def test_declined_card_does_not_activate(container, user):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        payment = container.billing.pay_with_card(session, entity, "tok-declined")
        assert (
            payment.status == PaymentStatus.FAILED
            and payment.error_message == "Carte refusée."
        )
        assert container.subscriptions.plan_for(session, entity).value == "free"
        assert InvoiceRepository(session).for_user(user) == []


def test_renewal_extends_current_period(container, user):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        container.billing.pay_with_card(session, entity, "tok-ok")
        first_end = container.subscriptions.current(session, user).current_period_end
        container.billing.pay_with_card(session, entity, "tok-ok")
        assert container.subscriptions.current(
            session, user
        ).current_period_end == first_end + timedelta(days=30)
        numbers = [i.number for i in InvoiceRepository(session).for_user(user)]
        assert numbers[0].endswith("000002") and numbers[1].endswith("000001")


def test_hosted_checkout_and_webhook(container, user, client):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        payment, url = container.billing.start_hosted_checkout(
            session, entity, "nowpayments"
        )
        order_id = payment.order_id
        assert url.endswith(order_id) and payment.status == PaymentStatus.PENDING
    body = json.dumps({"order_id": order_id, "status": "finished"})
    bad = client.post(
        "/webhooks/nowpayments", data=body, headers={"x-nowpayments-sig": "bad"}
    )
    assert bad.status_code == 400
    good = client.post(
        "/webhooks/nowpayments", data=body, headers={"x-nowpayments-sig": "good"}
    )
    assert good.status_code == 200 and good.get_json()["status"] == "succeeded"
    replay = client.post(
        "/webhooks/nowpayments", data=body, headers={"x-nowpayments-sig": "good"}
    )
    assert replay.status_code == 200
    with container.db.session_scope() as session:
        assert container.subscriptions.current(session, user) is not None
        assert len(InvoiceRepository(session).for_user(user)) == 1


def test_web_card_endpoint(logged_client):
    r = logged_client.post(
        "/abonnement/carte",
        json={"token": "tok-declined", "expected_amount_cents": 2000},
    )
    assert r.status_code == 402 and r.get_json()["code"] == "payment_failed"
    r = logged_client.post(
        "/abonnement/carte", json={"token": "tok-ok", "expected_amount_cents": 2000}
    )
    assert r.status_code == 200 and "/abonnement/merci" in r.get_json()["redirect"]
    assert logged_client.get("/api/me").get_json()["policy"]["plan"] == "premium"
    assert logged_client.get("/api/upcoming").status_code != 402


def test_expire_overdue(container, user):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        sub = container.subscriptions.activate(session, entity)
        sub.current_period_end = sub.started_at - timedelta(days=1)
    with container.db.session_scope() as session:
        assert container.subscriptions.expire_overdue(session) == 1
        assert container.subscriptions.current(session, user) is None
