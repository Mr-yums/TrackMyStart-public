"""Fabrique + registre des passerelles disponibles selon la configuration."""

from __future__ import annotations

from config import Settings
from yumnews.domain.enums import PaymentProvider
from yumnews.payments.gateway import CardGateway, HostedGateway, PaymentGateway


class GatewayRegistry:
    def __init__(self, gateways: list[PaymentGateway] | None = None) -> None:
        self._gateways: dict[PaymentProvider, PaymentGateway] = {}
        for gw in gateways or []:
            self.register(gw)

    def register(self, gateway: PaymentGateway) -> None:
        self._gateways[gateway.provider] = gateway

    def get(self, provider: PaymentProvider | str) -> PaymentGateway | None:
        return self._gateways.get(PaymentProvider(provider))

    @property
    def card(self) -> CardGateway | None:
        for gw in self._gateways.values():
            if isinstance(gw, CardGateway):
                return gw
        return None

    def hosted(self, provider: PaymentProvider | str) -> HostedGateway | None:
        gw = self.get(provider)
        return gw if isinstance(gw, HostedGateway) else None

    @property
    def hosted_gateways(self) -> list[HostedGateway]:
        return [gw for gw in self._gateways.values() if isinstance(gw, HostedGateway)]

    def available(self) -> list[dict]:
        return [
            {"provider": gw.provider.value, "label": gw.label}
            for gw in self._gateways.values()
        ]

    @classmethod
    def from_settings(cls, settings: Settings) -> "GatewayRegistry":
        registry = cls()
        if settings.square.enabled:
            from yumnews.payments.square_gateway import SquareGateway

            registry.register(SquareGateway(settings.square))
        if settings.nowpayments.enabled:
            from yumnews.payments.nowpayments_gateway import NowPaymentsGateway

            registry.register(NowPaymentsGateway(settings.nowpayments))
        return registry
