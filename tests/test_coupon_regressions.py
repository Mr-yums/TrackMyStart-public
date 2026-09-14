"""[Sol] Régressions : devis, réservations avant débit et utilisation atomique."""

import json
from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from test_coupons import _make_affiliate_coupon, _make_promo
from yumnews.domain.models import DiscordPassphrase, utcnow
from yumnews.repositories import CouponRepository, PassphraseRepository, UserRepository
from yumnews.services.errors import CouponError, PaymentError


def notify(container, session, order, status):
    return container.billing.handle_hosted_notification(
        session,
        "nowpayments",
        json.dumps({"order_id": order, "status": status}).encode(),
        "good",
    )


def test_pending_checkouts_reserve_all_five_periods(container, user):
    with container.db.session_scope() as session:
        _make_promo(session)
        entity = UserRepository(session).get(user)
        orders = [
            container.billing.start_hosted_checkout(
                session, entity, "nowpayments", "DECOUVERTE"
            )[0].order_id
            for _ in range(5)
        ]
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        with pytest.raises(CouponError):
            container.billing.start_hosted_checkout(
                session, entity, "nowpayments", "DECOUVERTE"
            )
        with pytest.raises(CouponError):
            container.billing.pay_with_card(
                session, entity, "tok-ok", coupon_code="DECOUVERTE"
            )
    assert container.gateways.card.requests == []
    for order in orders:
        with container.db.session_scope() as session:
            notify(container, session, order, "finished")
            notify(container, session, order, "finished")
    with container.db.session_scope() as session:
        coupon = CouponRepository(session).by_code("DECOUVERTE")
        assert CouponRepository(session).redemption_count(coupon.id) == 5
        assert CouponRepository(session).reserved_count(coupon.id) == 5


def test_global_limit_counts_pending_other_user_and_releases_failure(container, user):
    with container.db.session_scope() as session:
        _make_promo(session)
        CouponRepository(session).by_code("DECOUVERTE").max_redemptions = 1
        other = container.auth.register(
            session, "other@example.com", "motdepasse123", "Other"
        )
        other_id = other.id
        entity = UserRepository(session).get(user)
        order = container.billing.start_hosted_checkout(
            session, entity, "nowpayments", "DECOUVERTE"
        )[0].order_id
    with container.db.session_scope() as session:
        other = UserRepository(session).get(other_id)
        with pytest.raises(CouponError):
            container.billing.pay_with_card(
                session, other, "tok-ok", coupon_code="DECOUVERTE"
            )
        notify(container, session, order, "waiting")
        with pytest.raises(CouponError):
            container.billing.pay_with_card(
                session, other, "tok-ok", coupon_code="DECOUVERTE"
            )
        notify(container, session, order, "failed")
        declined = container.billing.pay_with_card(
            session, other, "tok-declined", coupon_code="DECOUVERTE"
        )
        assert declined.status == "failed"
        assert (
            container.billing.pay_with_card(
                session, other, "tok-ok", coupon_code="DECOUVERTE"
            ).amount_cents
            == 1600
        )
    with container.db.session_scope() as session:
        with pytest.raises(PaymentError):
            notify(container, session, order, "finished")


def test_quote_change_is_rejected_before_gateway(logged_client, container):
    with container.db.session_scope() as session:
        _make_affiliate_coupon(session)
    quote = logged_client.post("/abonnement/devis", json={"coupon": "RABAT"}).get_json()
    assert quote["amount_cents"] == 1200 and quote["currency"] == "EUR"
    with container.db.session_scope() as session:
        CouponRepository(session).by_code("RABAT").value = 1400
    response = logged_client.post(
        "/abonnement/carte",
        json={"token": "tok-ok", "coupon": "RABAT", "expected_amount_cents": 1200},
    )
    assert response.get_json()["code"] == "quote_changed"
    assert container.gateways.card.requests == []


@pytest.mark.parametrize("value", [None, True, "1200", -1])
def test_card_requires_valid_quote(logged_client, container, value):
    response = logged_client.post(
        "/abonnement/carte", json={"token": "tok-ok", "expected_amount_cents": value}
    )
    assert (
        response.status_code == 400 and response.get_json()["code"] == "quote_required"
    )
    assert container.gateways.card.requests == []


def test_empty_coupon_quotes_base_price(logged_client):
    data = logged_client.post("/abonnement/devis", json={"coupon": "  "}).get_json()
    assert data["ok"] and data["amount_cents"] == 2000 and data["discount_cents"] == 0


def test_claim_rejects_stale_session_after_another_claim(container, user):
    with container.db.session_scope() as session:
        phrase = "a" * 40
        session.add(DiscordPassphrase(user_id=user, phrase=phrase))
    with (
        Session(container.db.engine, expire_on_commit=False) as first,
        Session(container.db.engine, expire_on_commit=False) as second,
    ):
        a = PassphraseRepository(first).by_phrase(phrase)
        b = PassphraseRepository(second).by_phrase(phrase)
        assert a.status == b.status == "pending"
        assert (
            container.passphrases.claim(first, " " + phrase.upper() + " ").status
            == "claimed"
        )
        first.commit()
        assert container.passphrases.claim(second, phrase) is None
        second.commit()


def test_expired_seed_cannot_be_claimed(container, user):
    with container.db.session_scope() as session:
        session.add(
            DiscordPassphrase(
                user_id=user,
                phrase="b" * 40,
                expires_at=utcnow() - timedelta(seconds=1),
            )
        )
    with container.db.session_scope() as session:
        assert container.passphrases.claim(session, "b" * 40) is None
