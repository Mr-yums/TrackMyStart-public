"""Square Payments API (SDK ``squareup`` ≥ 40, classe ``Square``).

Repris de SearchMyJob (``SquarePaymentManager``) avec les corrections :
clé d'idempotence stable, échec réellement propagé, identifiant Square et
reçu conservés, environnement piloté par la configuration.
"""

from __future__ import annotations

import logging

from config import SquareSettings
from yumnews.domain.enums import PaymentProvider
from yumnews.payments.gateway import CardGateway, ChargeRequest, ChargeResult

log = logging.getLogger(__name__)


class SquareGateway(CardGateway):
    provider = PaymentProvider.SQUARE
    label = "Carte bancaire"

    def __init__(self, settings: SquareSettings) -> None:
        from square import Square
        from square.environment import SquareEnvironment

        env = (
            SquareEnvironment.PRODUCTION
            if settings.environment == "production"
            else SquareEnvironment.SANDBOX
        )
        self.settings = settings
        self._client = Square(token=settings.access_token, environment=env)

    def client_config(self) -> dict:
        return {
            "application_id": self.settings.application_id,
            "location_id": self.settings.location_id,
            "sandbox": self.settings.environment != "production",
        }

    def charge(self, request: ChargeRequest) -> ChargeResult:
        from square.core.api_error import ApiError

        params = dict(
            source_id=request.source_token,
            idempotency_key=request.order_id,
            amount_money={"amount": request.amount_cents, "currency": request.currency},
            location_id=self.settings.location_id,
            reference_id=request.order_id,
            note=request.description[:500],
            buyer_email_address=request.customer_email,
            autocomplete=True,
        )
        if request.verification_token:
            params["verification_token"] = request.verification_token
        try:
            response = self._client.payments.create(**params)
        except ApiError as exc:
            message = _first_error(getattr(exc, "body", None)) or str(exc)
            log.warning("Square refus : %s", message)
            return ChargeResult(
                succeeded=False,
                error_message=message,
                raw={"status_code": exc.status_code},
            )
        except Exception as exc:  # réseau, timeout…
            log.error("Square injoignable : %s", exc)
            return ChargeResult(
                succeeded=False,
                error_message="Service de paiement indisponible, réessayez.",
            )

        if response.errors:
            message = _first_error({"errors": [e.dict() for e in response.errors]})
            return ChargeResult(succeeded=False, error_message=message)
        # [Sol] Une autorisation seule ne constitue pas un encaissement terminé.
        payment = response.payment
        if payment is None or payment.status != "COMPLETED":
            return ChargeResult(
                succeeded=False,
                error_message="Paiement non abouti.",
                raw=_dump(payment),
            )
        card = (
            getattr(payment.card_details, "card", None)
            if payment.card_details
            else None
        )
        return ChargeResult(
            succeeded=True,
            provider_payment_id=payment.id,
            receipt_url=payment.receipt_url,
            card_brand=getattr(card, "card_brand", None),
            card_last4=getattr(card, "last_4", None),
            raw=_dump(payment),
        )


def _first_error(body: dict | None) -> str | None:
    if not body:
        return None
    errors = body.get("errors") or []
    if not errors:
        return None
    err = errors[0]
    return err.get("detail") or err.get("code") or "Erreur de paiement."


def _dump(obj) -> dict:
    try:
        return obj.dict() if obj is not None else {}
    except Exception:  # pragma: no cover
        return {}
