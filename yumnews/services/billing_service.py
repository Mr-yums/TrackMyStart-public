"""Façade de facturation : paiement → abonnement → facture → email, en une transaction.

Le contrôleur n'orchestre rien ; il appelle une méthode et lit le résultat.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from config import PremiumOffer
from yumnews.domain.enums import PaymentProvider, PaymentStatus
from yumnews.domain.models import Payment, User, utcnow
from yumnews.payments import ChargeRequest, GatewayRegistry, HostedNotification
from yumnews.repositories import PaymentRepository
from yumnews.services.coupon_service import CouponService
from yumnews.services.errors import PaymentError
from yumnews.services.invoice_service import InvoiceService
from yumnews.services.mailer import Email, Mailer
from yumnews.services.subscription_service import SubscriptionService

log = logging.getLogger(__name__)


class BillingService:
    def __init__(
        self,
        offer: PremiumOffer,
        gateways: GatewayRegistry,
        subscriptions: SubscriptionService,
        invoices: InvoiceService,
        coupons: CouponService,
        mailer: Mailer,
        site_url: str,
        site_name: str = "TrackMyStart",
        payments_enabled: bool = False,
    ) -> None:
        self.payments_enabled = payments_enabled
        self.offer = offer
        self.gateways = gateways
        self.subscriptions = subscriptions
        self.invoices = invoices
        self.coupons = coupons
        self.mailer = mailer
        self.site_url = site_url
        self.site_name = site_name

    def _require_open(self):
        if not self.payments_enabled:
            raise PaymentError(
                "Les paiements ne sont pas encore ouverts. La préinscription est gratuite.",
                code="payments_closed",
            )

    @property
    def description(self) -> str:
        return f"{self.site_name} Premium — {self.offer.period_days} jours"

    # ---- carte (Square) ---------------------------------------------
    def pay_with_card(
        self,
        session: Session,
        user: User,
        source_token: str,
        verification_token: str | None = None,
        coupon_code: str | None = None,
        expected_amount_cents: int | None = None,
    ) -> Payment:
        self._require_open()
        gateway = self.gateways.card
        if gateway is None:
            raise PaymentError("Le paiement par carte n'est pas disponible.")
        if not source_token:
            raise PaymentError("Jeton de carte manquant.")
        payment = self._new_payment(
            session, user, gateway.provider, coupon_code, expected_amount_cents
        )
        result = gateway.charge(
            ChargeRequest(
                order_id=payment.order_id,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                description=payment.description,
                customer_email=user.email,
                source_token=source_token,
                verification_token=verification_token,
            )
        )
        payment.provider_payment_id = result.provider_payment_id
        payment.receipt_url = result.receipt_url
        payment.card_brand = result.card_brand
        payment.card_last4 = result.card_last4
        payment.raw = result.raw or None
        if result.succeeded:
            self._finalize(session, payment)
        else:
            payment.status = PaymentStatus.FAILED
            payment.error_message = result.error_message
        session.flush()
        return payment

    # ---- hébergé (NOWPayments) --------------------------------------
    def start_hosted_checkout(
        self,
        session: Session,
        user: User,
        provider: str,
        coupon_code: str | None = None,
    ) -> tuple[Payment, str]:
        self._require_open()
        gateway = self.gateways.hosted(provider)
        if gateway is None:
            raise PaymentError("Moyen de paiement indisponible.")
        payment = self._new_payment(session, user, gateway.provider, coupon_code)
        checkout = gateway.create_checkout(
            ChargeRequest(
                order_id=payment.order_id,
                amount_cents=payment.amount_cents,
                currency=payment.currency,
                description=payment.description,
                customer_email=user.email,
                success_url=f"{self.site_url}/abonnement/merci?order={payment.order_id}",
                cancel_url=f"{self.site_url}/abonnement",
                notification_url=f"{self.site_url}/webhooks/{gateway.provider.value}",
            )
        )
        payment.provider_payment_id = checkout.provider_payment_id
        payment.raw = checkout.raw or None
        session.flush()
        return payment, checkout.redirect_url

    def handle_hosted_notification(
        self, session: Session, provider: str, body: bytes, signature: str | None
    ) -> Payment:
        # [Sol] La fermeture concerne les nouvelles commandes, jamais leur rapprochement signé.
        gateway = self.gateways.hosted(provider)
        if gateway is None:
            raise PaymentError("Fournisseur inconnu.")
        notification: HostedNotification = gateway.parse_notification(body, signature)
        payment = PaymentRepository(session).by_order_id(
            notification.order_id, for_update=True
        )
        if payment is None or payment.provider != gateway.provider:
            raise PaymentError("Commande inconnue.")
        # [Sol] Une signature valide ne remplace pas le contrôle du prix de la commande.
        if notification.succeeded and (
            notification.amount_cents != payment.amount_cents
            or notification.currency != payment.currency
        ):
            raise PaymentError("Montant ou devise IPN différents de la commande.")
        payment.provider_payment_id = (
            notification.provider_payment_id or payment.provider_payment_id
        )
        payment.raw = notification.raw or payment.raw
        if payment.status == PaymentStatus.SUCCEEDED:
            return payment  # notification rejouée : idempotent
        if payment.status in (PaymentStatus.FAILED, PaymentStatus.EXPIRED):
            # [Sol] Une place libérée ne peut être consommée par un événement contradictoire.
            if notification.succeeded:
                raise PaymentError(
                    "Succès reçu après un échec définitif : rapprochement manuel requis."
                )
            return payment
        if notification.succeeded:
            self._finalize(session, payment)
        elif notification.final:
            payment.status = PaymentStatus.FAILED
            payment.error_message = notification.error_message
        session.flush()
        return payment

    # ---- interne -----------------------------------------------------
    def _new_payment(
        self,
        session: Session,
        user: User,
        provider: PaymentProvider,
        coupon_code: str | None = None,
        expected_amount_cents: int | None = None,
    ) -> Payment:
        # Le prix vient toujours du serveur ; un coupon valide ne fait que le réduire.
        amount_cents = self.offer.price_cents
        coupon_id: int | None = None
        discount_cents = 0
        if coupon_code and coupon_code.strip():
            quote = self.coupons.quote(
                session, user, coupon_code, self.offer.price_cents, reserve=True
            )
            amount_cents = quote.amount_cents
            discount_cents = quote.discount_cents
            coupon_id = quote.coupon.id
        # [Sol] Vérifier le devis utilisé pour Square avant tout appel de débit.
        if expected_amount_cents is not None and expected_amount_cents != amount_cents:
            raise PaymentError(
                "Le tarif a changé. Vérifiez le nouveau montant avant de réessayer.",
                code="quote_changed",
            )
        payment = Payment(
            user_id=user.id,
            provider=provider,
            status=PaymentStatus.PENDING,
            amount_cents=amount_cents,
            currency=self.offer.currency,
            description=self.description,
            coupon_id=coupon_id,
            discount_cents=discount_cents,
        )
        return PaymentRepository(session).add(payment)

    def _finalize(self, session: Session, payment: Payment) -> None:
        payment.status = PaymentStatus.SUCCEEDED
        payment.error_message = None
        payment.updated_at = utcnow()
        user = payment.user
        subscription = self.subscriptions.activate(session, user, payment)
        invoice = self.invoices.issue(session, payment)
        self.coupons.redeem(
            session, payment
        )  # redemption + commission + passphrase (si rabatteur)
        session.flush()
        self._send_receipt(
            user, invoice.number, subscription.current_period_end.strftime("%d/%m/%Y")
        )

    def _send_receipt(self, user: User, invoice_number: str, period_end: str) -> None:
        try:
            self.mailer.send(
                Email(
                    to=user.email,
                    subject=f"{self.site_name} — merci pour votre abonnement",
                    text=(
                        f"Bonjour {user.display_name},\n\nVotre accès Premium est actif jusqu'au {period_end}.\n"
                        f"Facture n° {invoice_number} : {self.site_url}/compte/factures/{invoice_number}\n\nBon visionnage !"
                    ),
                )
            )
        except Exception as exc:  # l'email ne doit jamais faire échouer le paiement
            log.error("Envoi du reçu impossible : %s", exc)
