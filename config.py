"""Configuration de TrackMyStart : un objet immuable construit depuis l'environnement.

Le reste de l'application ne lit jamais ``os.environ`` directement ; il reçoit
un ``Settings`` (injection de dépendances), ce qui rend chaque composant
testable sans variables d'environnement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# [Sol] Configuration locale facultative ; aucun fichier .env réel dans le dépôt.
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_suffixed(name: str, suffix: str) -> str:
    """``NAME`` sinon ``NAME_<suffix>`` : les clés Square peuvent être séparées par environnement
    (``SQUARE_ACCESS_TOKEN_sandbox`` / ``_production``) sans renommage à l'injection."""
    return _env(name) or _env(f"{name}_{suffix}")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class SquareSettings:
    environment: str = "sandbox"
    access_token: str = ""
    application_id: str = ""
    location_id: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.access_token and self.location_id and self.application_id)


@dataclass(frozen=True)
class NowPaymentsSettings:
    api_key: str = ""
    ipn_secret: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.ipn_secret)


@dataclass(frozen=True)
class InvoiceIssuer:
    """Mentions de l'émetteur imprimées sur les factures (nom, adresse, n° TVA)."""

    name: str = "TrackMyStart"
    address: str = ""
    vat_number: str = ""
    vat_rate_percent: int = 20


@dataclass(frozen=True)
class PremiumOffer:
    price_cents: int = (
        2000  # [OXIO] tarif de base 20 € (les codes rabatteur/promo réduisent ce prix)
    )
    period_days: int = 30
    currency: str = "EUR"

    @property
    def price_label(self) -> str:
        return (
            f"{self.price_cents / 100:.2f}".replace(".", ",")
            + " "
            + ("€" if self.currency == "EUR" else self.currency)
        )


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    secret_key: str = "dev-secret"
    db_url: str = "sqlite:///" + str(BASE_DIR / "instance" / "yumnews.db")
    site_url: str = "http://localhost:8800"
    site_name: str = "TrackMyStart"
    tmdb_api_key: str = ""
    tmdb_language: str = "fr-FR"
    tmdb_region: str = "FR"
    trusted_proxy_hops: int = (
        0  # [Sol] Zéro en accès direct ; un derrière le Caddy privé.
    )
    cache_ttl: int = 3600
    advertising_path: str = str(BASE_DIR / "instance" / "advertising.json")  # [Sol]
    # [Sol] Activation explicite après configuration CMP et confidentialité.
    payments_enabled: bool = False  # [Sol] Préinscriptions, sans paiement.
    adsense_enabled: bool = False
    adsense_client: str = ""  # [Sol] Chaque installation utilise son propre compte.
    offer: PremiumOffer = field(default_factory=PremiumOffer)
    issuer: InvoiceIssuer = field(default_factory=InvoiceIssuer)
    square: SquareSettings = field(default_factory=SquareSettings)
    nowpayments: NowPaymentsSettings = field(default_factory=NowPaymentsSettings)
    # [Sol] Identifiants injectés par l’environnement privé de chaque installation.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = field(default="", repr=False)
    sendgrid_api_key: str = ""
    mail_from: str = "no-reply@trackmystart.de"
    # [OXIO] Rabatage : commission = % (après URSSAF) de chaque paiement amené par un code rabatteur.
    urssaf_rate_percent: int = 22
    affiliate_commission_percent: int = 21

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @classmethod
    def from_env(cls) -> "Settings":
        square_env = _env("SQUARE_ENV", "sandbox")
        site_name = _env("SITE_NAME", "TrackMyStart")
        return cls(
            env=_env("FLASK_ENV", "development"),
            secret_key=_env("SECRET_KEY", "dev-secret"),
            db_url=_env("DB_URL") or cls.db_url,
            site_url=_env("SITE_URL", "http://localhost:8800").rstrip("/"),
            site_name=site_name,
            tmdb_api_key=_env("TMDB_API_KEY"),
            tmdb_language=_env("TMDB_LANGUAGE", "fr-FR"),
            tmdb_region=_env("TMDB_REGION", "FR"),
            trusted_proxy_hops=_env_int("TRUSTED_PROXY_HOPS", 0),
            cache_ttl=_env_int("CACHE_TTL_SECONDS", 3600),
            advertising_path=_env("ADS_CONFIG_PATH") or cls.advertising_path,
            payments_enabled=_env("PAYMENTS_ENABLED", "false").lower() == "true",
            adsense_enabled=_env("ADSENSE_ENABLED", "false").lower() == "true",
            adsense_client=_env("ADSENSE_CLIENT") or cls.adsense_client,
            offer=PremiumOffer(
                price_cents=_env_int("PREMIUM_PRICE_CENTS", 2000),
                period_days=_env_int("PREMIUM_PERIOD_DAYS", 30),
                currency=_env("PREMIUM_CURRENCY", "EUR"),
            ),
            issuer=InvoiceIssuer(
                name=_env("INVOICE_ISSUER_NAME", site_name),
                address=_env("INVOICE_ISSUER_ADDRESS"),
                vat_number=_env("INVOICE_ISSUER_VAT"),
                vat_rate_percent=_env_int("INVOICE_VAT_RATE", 20),
            ),
            square=SquareSettings(
                environment=square_env,
                access_token=_env_suffixed("SQUARE_ACCESS_TOKEN", square_env),
                application_id=_env_suffixed("SQUARE_APPLICATION_ID", square_env),
                location_id=_env_suffixed("SQUARE_LOCATION_ID", square_env),
            ),
            nowpayments=NowPaymentsSettings(
                api_key=_env("NOWPAYMENTS_API_KEY"),
                ipn_secret=_env("NOWPAYMENTS_IPN_SECRET"),
            ),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=_env_int("SMTP_PORT", 587),
            smtp_username=_env("SMTP_USERNAME"),
            smtp_password=_env("TRACKMYSTART_SMTP_PASSWORD"),
            sendgrid_api_key=_env("SENDGRID_API_KEY"),
            mail_from=_env("MAIL_FROM", "no-reply@trackmystart.de"),
            urssaf_rate_percent=_env_int("URSSAF_RATE_PERCENT", 22),
            affiliate_commission_percent=_env_int("AFFILIATE_COMMISSION_PERCENT", 21),
        )
