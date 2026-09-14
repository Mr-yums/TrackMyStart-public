"""Abonnement Premium : page de paiement, débit carte (Square), crypto (NOWPayments), webhooks."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from yumnews.domain.enums import PaymentStatus
from yumnews.repositories import PaymentRepository
from yumnews.services.errors import DomainError, PaymentError, ValidationError
from yumnews.web.context import container, db_session, json_body, login_required_json

log = logging.getLogger(__name__)
billing_bp = Blueprint("billing", __name__, url_prefix="/abonnement")
webhooks_bp = Blueprint("webhooks", __name__, url_prefix="/webhooks")


# [Sol] Bloquer les appels directs avant tout accès aux passerelles. Les retours
# signés d’anciennes opérations et l’historique restent traités normalement.
@billing_bp.before_request
def payment_launch_gate():
    if container().settings.payments_enabled:
        return None
    if request.endpoint == "billing.checkout":
        return redirect(url_for("public.preregistration"))
    if request.endpoint in {
        "billing.quote",
        "billing.pay_with_card",
        "billing.start_hosted",
    }:
        return jsonify(
            ok=False,
            code="payments_closed",
            error="Les paiements ne sont pas encore ouverts.",
            redirect=url_for("public.preregistration"),
        ), 503


@billing_bp.get("")
@login_required
def checkout():
    c = container()
    card = c.gateways.card
    return render_template(
        "billing/checkout.html",
        subscription=c.subscriptions.summary(db_session(), current_user.entity),
        card_config=card.client_config() if card else None,
        hosted=[
            {"provider": gw.provider.value, "label": gw.label}
            for gw in c.gateways.hosted_gateways
        ],
    )


@billing_bp.post("/devis")
@login_required_json
def quote():
    """Prévisualise le prix après application d'un code promo (carte ou crypto), sans payer."""
    body = json_body()
    c = container()
    try:
        with c.db.session_scope() as session:
            code = str(body.get("coupon") or "").strip()
            amount_cents, discount_cents = c.settings.offer.price_cents, 0
            if code:
                q = c.billing.coupons.quote(
                    session, current_user.entity, code, amount_cents
                )
                amount_cents, discount_cents = q.amount_cents, q.discount_cents
    except DomainError as exc:
        return jsonify(ok=False, error=exc.message, code=exc.code), exc.status_code
    return jsonify(
        ok=True,
        amount_cents=amount_cents,
        currency=c.settings.offer.currency,
        discount_cents=discount_cents,
        amount_label=f"{amount_cents / 100:.2f}".replace(".", ",") + " €",
    )


@billing_bp.post("/carte")
@login_required_json
def pay_with_card():
    body = json_body()
    c = container()
    try:
        # [Sol] Le client confirme le montant du devis utilisé pour la tokenisation.
        expected = body.get("expected_amount_cents")
        if type(expected) is not int or expected < 0:
            raise ValidationError(
                "Montant du devis manquant ou invalide.", code="quote_required"
            )
        with c.db.session_scope() as session:
            payment = c.billing.pay_with_card(
                session,
                current_user.entity,
                str(body.get("token") or ""),
                body.get("verification_token") or None,
                coupon_code=body.get("coupon") or None,
                expected_amount_cents=expected,
            )
            status, error, order_id = (
                payment.status,
                payment.error_message,
                payment.order_id,
            )
    except DomainError as exc:
        return jsonify(ok=False, error=exc.message, code=exc.code), exc.status_code
    if status != PaymentStatus.SUCCEEDED:
        return jsonify(
            ok=False,
            error=error or "Paiement refusé.",
            code="payment_failed",
            order_id=order_id,
        ), 402
    return jsonify(
        ok=True, order_id=order_id, redirect=url_for("billing.thanks", order=order_id)
    )


@billing_bp.post("/hebergé/<provider>")
@billing_bp.post("/hosted/<provider>")
@login_required
def start_hosted(provider: str):
    c = container()
    coupon_code = request.form.get("coupon") or None
    try:
        with c.db.session_scope() as session:
            _payment, redirect_url = c.billing.start_hosted_checkout(
                session, current_user.entity, provider, coupon_code=coupon_code
            )
    except DomainError as exc:
        return render_template(
            "public/error.html", title="Paiement", message=exc.message
        ), exc.status_code
    return redirect(redirect_url)


@billing_bp.get("/merci")
@login_required
def thanks():
    order_id = request.args.get("order", "")
    payment = (
        PaymentRepository(db_session()).by_order_id(order_id) if order_id else None
    )
    if payment is not None and payment.user_id != current_user.id:
        payment = None
    return render_template("billing/thanks.html", payment=payment)


@billing_bp.get("/statut/<order_id>")
@login_required_json
def status(order_id: str):
    payment = PaymentRepository(db_session()).by_order_id(order_id)
    if payment is None or payment.user_id != current_user.id:
        return jsonify(ok=False, error="Commande inconnue."), 404
    return jsonify(
        ok=True,
        status=payment.status.value
        if hasattr(payment.status, "value")
        else payment.status,
    )


@webhooks_bp.post("/<provider>")
def hosted_webhook(provider: str):
    c = container()
    signature = request.headers.get("x-nowpayments-sig") or request.headers.get(
        "X-Signature"
    )
    try:
        with c.db.session_scope() as session:
            payment = c.billing.handle_hosted_notification(
                session, provider, request.get_data(), signature
            )
            status = payment.status
    except PaymentError as exc:
        log.warning("Webhook %s rejeté : %s", provider, exc.message)
        return jsonify(ok=False, error=exc.message), 400
    return jsonify(ok=True, status=status.value if hasattr(status, "value") else status)
