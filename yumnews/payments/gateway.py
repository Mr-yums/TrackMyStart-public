"""Abstractions de paiement (pattern Strategy).

Deux familles de passerelles :

* :class:`CardGateway` — débit synchrone d'un jeton de carte (Square Web Payments SDK).
* :class:`HostedGateway` — redirection vers une page hébergée + notification
  serveur signée (NOWPayments pour la crypto).

Le service de facturation ne connaît que ces interfaces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from yumnews.domain.enums import PaymentProvider


@dataclass(frozen=True)
class ChargeRequest:
    order_id: str  # sert de clé d'idempotence — stable pour une même commande
    amount_cents: int
    currency: str
    description: str
    customer_email: str
    source_token: str = ""  # jeton carte (Square) ; vide pour une passerelle hébergée
    verification_token: str | None = None  # SCA / 3-D Secure (Square verifyBuyer)
    success_url: str = ""
    cancel_url: str = ""
    notification_url: str = ""


@dataclass(frozen=True)
class ChargeResult:
    succeeded: bool
    provider_payment_id: str | None = None
    receipt_url: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    error_message: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HostedCheckout:
    provider_payment_id: str
    redirect_url: str
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HostedNotification:
    order_id: str
    provider_payment_id: str
    succeeded: bool
    final: bool  # True si l'état ne changera plus (payé, expiré, échoué)
    error_message: str | None = None
    raw: dict = field(default_factory=dict)
    amount_cents: int | None = None  # [Sol] Prix fiat signé, comparé à la commande.
    currency: str = ""


class PaymentGateway(ABC):
    provider: PaymentProvider
    label: str

    @abstractmethod
    def client_config(self) -> dict:
        """Ce que le navigateur a le droit de connaître (identifiants publics)."""


class CardGateway(PaymentGateway):
    @abstractmethod
    def charge(self, request: ChargeRequest) -> ChargeResult: ...


class HostedGateway(PaymentGateway):
    @abstractmethod
    def create_checkout(self, request: ChargeRequest) -> HostedCheckout: ...

    @abstractmethod
    def parse_notification(
        self, body: bytes, signature: str | None
    ) -> HostedNotification:
        """Vérifie la signature puis normalise la notification. Lève PaymentError sinon."""
