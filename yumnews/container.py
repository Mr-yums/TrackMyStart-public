"""Composition racine : construit chaque dépendance une seule fois."""

from __future__ import annotations

from config import Settings
from yumnews.catalog.anilist.client import AnimeScheduleClient
from yumnews.catalog.cache import TtlCache
from yumnews.catalog.http import HttpClient
from yumnews.catalog.mangadex.client import MangaDexClient
from yumnews.catalog.news.client import NewsClient
from yumnews.catalog.news.reader import PressReader  # [Sol]
from yumnews.catalog.service import CatalogService
from yumnews.catalog.tmdb.client import TmdbClient
from yumnews.database import Database
from yumnews.payments import GatewayRegistry
from yumnews.services.auth_service import AuthService
from yumnews.services.advertising import Advertising  # [Sol]
from yumnews.services.billing_service import BillingService
from yumnews.services.coupon_service import CouponService
from yumnews.services.invoice_service import InvoiceService
from yumnews.services.smtp_mailer import SMTPMailer  # [Sol]
from yumnews.services.mailer import LoggingMailer, Mailer, SendGridMailer
from yumnews.services.member_service import MemberService
from yumnews.services.catalog_preferences import CatalogPreferences  # [Sol]
from yumnews.services.passphrase_service import PassphraseService
from yumnews.services.preference_service import PreferenceService
from yumnews.services.reader_suggestions import ReaderSuggestions  # [Sol]
from yumnews.services.recommendation_service import RecommendationService  # [Sol]
from yumnews.services.security import PasswordHasher, TokenService
from yumnews.services.subscription_service import SubscriptionService


class Container:
    def __init__(
        self,
        settings: Settings,
        gateways: GatewayRegistry | None = None,
        mailer: Mailer | None = None,
    ) -> None:
        self.settings = settings
        self.db = Database(settings.db_url)
        self.cache = TtlCache(default_ttl=settings.cache_ttl)
        self.http = HttpClient(
            user_agent=f"{settings.site_name}/1.0 (+{settings.site_url})"
        )

        self.tmdb = TmdbClient(
            settings.tmdb_api_key,
            self.http,
            self.cache,
            settings.tmdb_language,
            settings.tmdb_region,
        )
        self.mangadex = MangaDexClient(self.http, self.cache)
        self.press_reader = PressReader(settings.secret_key)
        self.news = NewsClient(self.http, self.cache, reader=self.press_reader)
        self.anilist = AnimeScheduleClient(self.http, self.cache)
        self.catalog = CatalogService(self.tmdb, self.mangadex, self.news, self.anilist)

        self.mailer: Mailer = mailer or (
            SendGridMailer(settings.sendgrid_api_key, settings.mail_from)
            if settings.sendgrid_api_key
            else LoggingMailer()
        )
        if mailer is None and settings.smtp_host:
            self.mailer = SMTPMailer(
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_username,
                settings.smtp_password,
                settings.mail_from,
            )
        self.tokens = TokenService(settings.secret_key)
        self.auth = AuthService(
            PasswordHasher(),
            self.tokens,
            self.mailer,
            settings.site_url,
            settings.site_name,
        )
        self.subscriptions = SubscriptionService(settings.offer.period_days)
        self.invoices = InvoiceService(settings.issuer)
        self.passphrases = PassphraseService()
        self.coupons = CouponService(settings.urssaf_rate_percent, self.passphrases)
        self.gateways = gateways or GatewayRegistry.from_settings(settings)
        self.billing = BillingService(
            settings.offer,
            self.gateways,
            self.subscriptions,
            self.invoices,
            self.coupons,
            self.mailer,
            settings.site_url,
            settings.site_name,
            payments_enabled=settings.payments_enabled,
        )
        self.advertising = Advertising(settings.advertising_path)
        self.members = MemberService()
        self.catalog_preferences = CatalogPreferences()
        self.preferences = PreferenceService()  # [Sol]
        self.recommendations = RecommendationService(settings.secret_key)
        self.reader_suggestions = ReaderSuggestions(settings.secret_key)
