from yumnews.repositories.affiliate_repository import (
    AffiliateReport,
    AffiliateRepository,
)
from yumnews.repositories.base import Repository
from yumnews.repositories.coupon_repository import CouponRepository
from yumnews.repositories.follow_repository import FollowRepository
from yumnews.repositories.invoice_repository import InvoiceRepository
from yumnews.repositories.login_attempt_repository import LoginAttemptRepository
from yumnews.repositories.passphrase_repository import PassphraseRepository
from yumnews.repositories.payment_repository import PaymentRepository
from yumnews.repositories.subscription_repository import SubscriptionRepository
from yumnews.repositories.user_repository import UserRepository
from yumnews.repositories.watchlist_repository import WatchlistRepository

__all__ = [
    "Repository",
    "AffiliateReport",
    "AffiliateRepository",
    "CouponRepository",
    "FollowRepository",
    "InvoiceRepository",
    "LoginAttemptRepository",
    "PassphraseRepository",
    "PaymentRepository",
    "SubscriptionRepository",
    "UserRepository",
    "WatchlistRepository",
]
