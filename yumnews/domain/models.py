"""Modèles ORM (SQLAlchemy 2.0, typés). Le SQL ne vit que dans ``repositories``."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from yumnews.domain.enums import (
    CouponKind,
    CouponStatus,
    MediaType,
    PassphraseStatus,
    PaymentProvider,
    PaymentStatus,
    Plan,
    SubscriptionStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """[Sol] Stocke en UTC et rétablit le fuseau omis par SQLite à la lecture."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Subscription.id.desc()",
    )
    follows: Mapped[list["Follow"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    watchlist: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.id} {self.email}>"


class Subscription(TimestampMixin, Base):
    """Une période d'abonnement payée. Le plan courant se lit via ``SubscriptionRepository``."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan: Mapped[Plan] = mapped_column(String(20), default=Plan.PREMIUM, nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        String(20), default=SubscriptionStatus.ACTIVE, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )
    current_period_end: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    canceled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL")
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    payment: Mapped["Payment | None"] = relationship()

    def is_current(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        return (
            self.status == SubscriptionStatus.ACTIVE and self.current_period_end > now
        )


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(
        String(64), default=new_uuid, unique=True, nullable=False
    )
    provider: Mapped[PaymentProvider] = mapped_column(String(20), nullable=False)
    provider_payment_id: Mapped[str | None] = mapped_column(String(128), index=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[PaymentStatus] = mapped_column(
        String(20), default=PaymentStatus.PENDING, nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    coupon_id: Mapped[int | None] = mapped_column(
        ForeignKey("coupons.id", ondelete="SET NULL"), index=True
    )
    # [Sol] Valeur SQL pour les paiements créés par une ancienne version après migration.
    discount_cents: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    receipt_url: Mapped[str | None] = mapped_column(String(512))
    card_brand: Mapped[str | None] = mapped_column(String(40))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    error_message: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict | None] = mapped_column(JSON)

    user: Mapped[User] = relationship(back_populates="payments")
    invoice: Mapped["Invoice | None"] = relationship(
        back_populates="payment", uselist=False
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    amount_ht_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_ttc_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="EUR", nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    payment: Mapped[Payment] = relationship(back_populates="invoice")


class Follow(Base):
    """Un acteur / réalisateur suivi par un membre (personne TMDB)."""

    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("user_id", "person_id", name="uq_follow_user_person"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_path: Mapped[str | None] = mapped_column(String(255))
    department: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="follows")


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    __table_args__ = (
        UniqueConstraint("user_id", "media_type", "media_id", name="uq_watchlist_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_type: Mapped[MediaType] = mapped_column(String(10), nullable=False)
    media_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    poster: Mapped[str | None] = mapped_column(String(512))
    year: Mapped[str | None] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="watchlist")


class LoginAttempt(Base):
    """Compteur d'échecs de connexion par (email, IP) — anti force brute."""

    __tablename__ = "login_attempts"
    __table_args__ = (UniqueConstraint("email", "ip_address", name="uq_login_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime())


class InvoiceCounter(Base):
    """Une ligne par année : garantit une numérotation continue des factures."""

    __tablename__ = "invoice_counters"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), onupdate=utcnow
    )


class UserPreferences(TimestampMixin, Base):
    """[Sol] Préférences propres à un membre, sans modifier les comptes existants."""

    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class InvoiceSnapshot(Base):
    """[Sol] Mentions figées lors de l'émission, indépendantes des futurs réglages."""

    __tablename__ = "invoice_snapshots"
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), primary_key=True
    )
    details: Mapped[dict] = mapped_column(JSON, nullable=False)


class Affiliate(TimestampMixin, Base):
    """Rabatteur : apporteur d'affaires rémunéré à la commission sur chaque paiement amené."""

    __tablename__ = "affiliates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    # Commission due au rabatteur, en % de ce qui reste après l'URSSAF (figée à chaque redemption).
    commission_percent: Mapped[int] = mapped_column(Integer, default=21, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    coupons: Mapped[list["Coupon"]] = relationship(back_populates="affiliate")
    redemptions: Mapped[list["Redemption"]] = relationship(back_populates="affiliate")


class Coupon(TimestampMixin, Base):
    """Code de réduction. Rattaché à un rabatteur (``affiliate_id``) ou promo générique."""

    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("code", name="uq_coupon_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    kind: Mapped[CouponKind] = mapped_column(String(20), nullable=False)
    # PERCENT → pourcentage de remise ; FIXED → prix final en centimes.
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[CouponStatus] = mapped_column(
        String(20), default=CouponStatus.ACTIVE, nullable=False
    )
    affiliate_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliates.id", ondelete="SET NULL"), index=True
    )
    # None = illimité (code rabatteur : 12 € à chaque mois) ; 5 = promo découverte (5 premiers mois).
    max_periods_per_user: Mapped[int | None] = mapped_column(Integer)
    # Plafond global d'utilisations (optionnel).
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    affiliate: Mapped["Affiliate | None"] = relationship(back_populates="coupons")
    redemptions: Mapped[list["Redemption"]] = relationship(
        back_populates="coupon", cascade="all, delete-orphan"
    )


class Redemption(TimestampMixin, Base):
    """Une utilisation d'un coupon ayant abouti à un paiement réussi ; commission figée."""

    __tablename__ = "redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coupon_id: Mapped[int] = mapped_column(
        ForeignKey("coupons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    affiliate_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliates.id", ondelete="SET NULL"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # montant réellement payé (réduit)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    urssaf_rate_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    coupon: Mapped[Coupon] = relationship(back_populates="redemptions")
    affiliate: Mapped["Affiliate | None"] = relationship(back_populates="redemptions")


class DiscordPassphrase(TimestampMixin, Base):
    """Seed copiable-collable remis au client venu via un rabatteur, pour entrer sur le Discord.

    Une seule passphrase active par client. Le futur bot la valide (usage unique via ``status``).
    """

    __tablename__ = "discord_passphrases"
    __table_args__ = (UniqueConstraint("phrase", name="uq_passphrase_phrase"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    affiliate_id: Mapped[int | None] = mapped_column(
        ForeignKey("affiliates.id", ondelete="SET NULL"), index=True
    )
    redemption_id: Mapped[int | None] = mapped_column(
        ForeignKey("redemptions.id", ondelete="SET NULL")
    )
    phrase: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    status: Mapped[PassphraseStatus] = mapped_column(
        String(20), default=PassphraseStatus.PENDING, nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
