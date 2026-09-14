from __future__ import annotations

import enum


class Plan(str, enum.Enum):
    FREE = "free"
    PREMIUM = "premium"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELED = "canceled"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class PaymentProvider(str, enum.Enum):
    SQUARE = "square"
    NOWPAYMENTS = "nowpayments"
    MANUAL = "manual"


class MediaType(str, enum.Enum):
    MOVIE = "movie"
    TV = "tv"
    MANGA = "manga"


class CouponKind(str, enum.Enum):
    PERCENT = "percent"  # value = pourcentage de remise (ex. 20 → -20 %)
    FIXED = "fixed"  # value = prix final en centimes (ex. 1200 → 12,00 €)


class CouponStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PassphraseStatus(str, enum.Enum):
    PENDING = "pending"  # remise au client, pas encore consommée côté Discord
    CLAIMED = "claimed"  # le bot Discord l'a validée (usage unique)
