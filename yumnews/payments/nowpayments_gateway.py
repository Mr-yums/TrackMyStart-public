"""NOWPayments (crypto) : facture hébergée + IPN signée HMAC-SHA512."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal, InvalidOperation
import logging

import requests

from config import NowPaymentsSettings
from yumnews.domain.enums import PaymentProvider
from yumnews.payments.gateway import (
    ChargeRequest,
    HostedCheckout,
    HostedGateway,
    HostedNotification,
)
from yumnews.services.errors import PaymentError

log = logging.getLogger(__name__)

FINAL_SUCCESS = {"finished"}  # [Sol] confirmed est encore une confirmation blockchain.
FINAL_FAILURE = {"failed", "expired", "refunded"}


class NowPaymentsGateway(HostedGateway):
    provider = PaymentProvider.NOWPAYMENTS
    label = "Crypto (USDT, XMR…)"
    BASE_URL = "https://api.nowpayments.io/v1"

    def __init__(self, settings: NowPaymentsSettings, timeout: int = 15) -> None:
        self.settings = settings
        self.timeout = timeout

    def client_config(self) -> dict:
        return {}

    def create_checkout(self, request: ChargeRequest) -> HostedCheckout:
        payload = {
            "price_amount": round(request.amount_cents / 100, 2),
            "price_currency": request.currency.lower(),
            "order_id": request.order_id,
            "order_description": request.description[:200],
            "ipn_callback_url": request.notification_url,
            "success_url": request.success_url,
            "cancel_url": request.cancel_url,
        }
        try:
            response = requests.post(
                f"{self.BASE_URL}/invoice",
                json=payload,
                headers={"x-api-key": self.settings.api_key},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            log.error("NOWPayments injoignable : %s", exc)
            raise PaymentError(
                "Service crypto indisponible, réessayez plus tard."
            ) from exc
        if response.status_code >= 300:
            log.warning(
                "NOWPayments %s : %s", response.status_code, response.text[:300]
            )
            raise PaymentError("Impossible de créer la facture crypto.")
        data = response.json()
        if not data.get("invoice_url"):
            raise PaymentError("Réponse NOWPayments incomplète.")
        return HostedCheckout(
            provider_payment_id=str(data.get("id")),
            redirect_url=data["invoice_url"],
            raw=data,
        )

    def parse_notification(
        self, body: bytes, signature: str | None
    ) -> HostedNotification:
        if not signature:
            raise PaymentError("Signature IPN absente.")
        try:
            data = json.loads(body)
        except ValueError:
            raise PaymentError("IPN illisible.") from None
        if not isinstance(data, dict):
            raise PaymentError("Objet IPN attendu.")
        expected = self.sign(data)
        if not hmac.compare_digest(expected, signature.strip()):
            raise PaymentError("Signature IPN invalide.")
        status = str(data.get("payment_status", "")).lower()
        succeeded = status in FINAL_SUCCESS
        final = succeeded or status in FINAL_FAILURE
        amount_cents = None
        if succeeded:
            try:
                value = Decimal(str(data.get("price_amount"))) * 100
                if (
                    not value.is_finite()
                    or value < 0
                    or value != value.to_integral_value()
                ):
                    raise ValueError()
                amount_cents = int(value)
            except (InvalidOperation, ValueError, TypeError):
                raise PaymentError("Montant IPN invalide.") from None
        return HostedNotification(
            amount_cents=amount_cents,
            currency=str(data.get("price_currency", "")).upper(),
            order_id=str(data.get("order_id", "")),
            provider_payment_id=str(data.get("payment_id", "")),
            succeeded=succeeded,
            final=final,
            error_message=None if succeeded else f"Statut NOWPayments : {status}",
            raw=data,
        )

    def sign(self, data: dict) -> str:
        message = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hmac.new(
            self.settings.ipn_secret.encode(), message.encode(), hashlib.sha512
        ).hexdigest()
