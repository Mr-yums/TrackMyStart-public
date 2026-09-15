"""Coupons, rabatteurs (commission après URSSAF) et passphrases Discord.

Prix de base : 2000 (20 €). Code rabatteur → prix fixe 12 € + commission + passphrase ;
promo découverte → -20 % plafonnée par compte ; paiement refusé → aucune redemption.
"""

import pytest

from yumnews.domain.enums import CouponKind, PassphraseStatus, PaymentStatus
from yumnews.domain.models import Affiliate, Coupon
from yumnews.repositories import (
    AffiliateRepository,
    CouponRepository,
    InvoiceRepository,
    PassphraseRepository,
    UserRepository,
)
from yumnews.services.errors import CouponError


def _make_affiliate_coupon(
    session, code="RABAT", price_cents=1200, commission_percent=21
):
    affiliate = Affiliate(
        name="Rabatteur Test",
        email="rab@example.com",
        commission_percent=commission_percent,
    )
    session.add(affiliate)
    session.flush()
    session.add(
        Coupon(
            code=code,
            kind=CouponKind.FIXED,
            value=price_cents,
            affiliate_id=affiliate.id,
        )
    )
    session.flush()
    return affiliate


def _make_promo(session, code="DECOUVERTE", percent=20, max_per_user=5):
    session.add(
        Coupon(
            code=code,
            kind=CouponKind.PERCENT,
            value=percent,
            max_periods_per_user=max_per_user,
        )
    )
    session.flush()


def test_affiliate_code_charges_fixed_price_with_commission_and_passphrase(
    container, user
):
    with container.db.session_scope() as session:
        _make_affiliate_coupon(session)
        entity = UserRepository(session).get(user)
        payment = container.billing.pay_with_card(
            session, entity, "tok-ok", coupon_code="rabat"
        )
        # Prix fixe 12 € (au lieu de 20 €), remise figée.
        assert (
            payment.status == PaymentStatus.SUCCEEDED
            and payment.amount_cents == 1200
            and payment.discount_cents == 800
        )
        invoice = InvoiceRepository(session).for_user(user)[0]
        assert invoice.amount_ttc_cents == 1200
        # Commission = 21 % de (1200 - 22 % URSSAF) = 21 % de 936 = 197 cents.
        affiliate_id = CouponRepository(session).get(payment.coupon_id).affiliate_id
        report = AffiliateRepository(session).report(affiliate_id)
        assert report.distinct_clients == 1 and report.paid_redemptions == 1
        assert report.revenue_cents == 1200 and report.commission_cents == 197
        # Une passphrase Discord a été générée pour ce client.
        passphrase = PassphraseRepository(session).active_for_user(user)
        assert (
            passphrase is not None
            and len(passphrase.phrase) == 40
            and passphrase.phrase.isalnum()
        )
    assert container.gateways.card.requests[-1].amount_cents == 1200


def test_discovery_promo_applies_percent_discount(container, user):
    with container.db.session_scope() as session:
        _make_promo(session)
        entity = UserRepository(session).get(user)
        payment = container.billing.pay_with_card(
            session, entity, "tok-ok", coupon_code="decouverte"
        )
        # 20 € -20 % = 16 €, pas de rabatteur → pas de commission ni de passphrase.
        assert payment.amount_cents == 1600 and payment.discount_cents == 400
        assert PassphraseRepository(session).active_for_user(user) is None


def test_promo_capped_per_user(container, user):
    with container.db.session_scope() as session:
        _make_promo(session, code="UNSEUL", max_per_user=1)
        entity = UserRepository(session).get(user)
        container.billing.pay_with_card(session, entity, "tok-ok", coupon_code="unseul")
        # Deuxième tentative : plafond par compte atteint.
        with pytest.raises(CouponError) as exc:
            container.billing.pay_with_card(
                session, entity, "tok-ok", coupon_code="unseul"
            )
        assert exc.value.code == "coupon_exhausted"


def test_invalid_coupon_rejected(container, user):
    with container.db.session_scope() as session:
        entity = UserRepository(session).get(user)
        with pytest.raises(CouponError) as exc:
            container.billing.pay_with_card(
                session, entity, "tok-ok", coupon_code="NOPE"
            )
        assert exc.value.code == "coupon_invalid"


def test_declined_card_does_not_redeem_or_issue_passphrase(container, user):
    with container.db.session_scope() as session:
        _make_affiliate_coupon(session, code="RAB2")
        entity = UserRepository(session).get(user)
        payment = container.billing.pay_with_card(
            session, entity, "tok-declined", coupon_code="rab2"
        )
        assert payment.status == PaymentStatus.FAILED
        coupon = CouponRepository(session).by_code("RAB2")
        assert CouponRepository(session).redemption_count(coupon.id) == 0
        assert PassphraseRepository(session).active_for_user(user) is None


def test_passphrase_is_single_use(container, user):
    with container.db.session_scope() as session:
        _make_affiliate_coupon(session, code="RAB3")
        entity = UserRepository(session).get(user)
        container.billing.pay_with_card(session, entity, "tok-ok", coupon_code="rab3")
        phrase = PassphraseRepository(session).active_for_user(user).phrase
    with container.db.session_scope() as session:
        claimed = container.passphrases.claim(
            session, phrase.upper()
        )  # insensible à la casse/espaces
        assert claimed is not None and claimed.status == PassphraseStatus.CLAIMED
    with container.db.session_scope() as session:
        assert container.passphrases.claim(session, phrase) is None  # déjà utilisée


def test_web_quote_and_card_endpoint_with_coupon(logged_client, container):
    with container.db.session_scope() as session:
        _make_promo(session, code="WEB20", max_per_user=5)
    devis = logged_client.post("/abonnement/devis", json={"coupon": "web20"})
    assert devis.status_code == 200 and devis.get_json()["amount_cents"] == 1600
    bad = logged_client.post("/abonnement/devis", json={"coupon": "inexistant"})
    assert bad.status_code == 400 and bad.get_json()["code"] == "coupon_invalid"
    paid = logged_client.post(
        "/abonnement/carte",
        json={"token": "tok-ok", "coupon": "web20", "expected_amount_cents": 1600},
    )
    assert paid.status_code == 200
    # Promo (sans rabatteur) → aucun seed premium affiché dans le profil.
    assert b"Acc\xc3\xa8s Discord premium" not in logged_client.get("/compte").data


def test_account_page_shows_discord_seed_for_affiliate_client(
    logged_client, container, user
):
    with container.db.session_scope() as session:
        _make_affiliate_coupon(session, code="PROFIL12")
        entity = UserRepository(session).get(user)
        container.billing.pay_with_card(
            session, entity, "tok-ok", coupon_code="profil12"
        )
        seed = PassphraseRepository(session).active_for_user(user).phrase
    page = logged_client.get("/compte")
    assert (
        page.status_code == 200
        and b"Acc\xc3\xa8s Discord premium" in page.data
        and seed.encode() in page.data
    )
