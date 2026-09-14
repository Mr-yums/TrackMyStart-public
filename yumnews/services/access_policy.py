"""Politique d'accès : pattern Strategy.

Une seule question est posée partout dans l'application : « ce membre
peut-il faire X, et jusqu'à quelle limite ? ». Les réponses sont regroupées
ici au lieu d'être copiées dans chaque contrôleur (défaut vu dans SearchMyJob).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from yumnews.domain.enums import Plan
from yumnews.services.errors import AccessDeniedError

UNLIMITED = 10**9


@dataclass(frozen=True)
class Limits:
    max_follows: int
    max_watchlist: int
    news_sources_per_category: int
    news_articles_per_source: int
    news_categories: tuple[str, ...] | None  # None = toutes
    catalog_pages: int  # nb de pages TMDB explorables par liste


class AccessPolicy(ABC):
    plan: Plan
    label: str
    limits: Limits
    features: frozenset[str]

    def can(self, feature: str) -> bool:
        return feature in self.features

    def require(self, feature: str) -> None:
        if not self.can(feature):
            raise AccessDeniedError(
                f"La fonctionnalité « {FEATURE_LABELS.get(feature, feature)} » est réservée aux membres Premium.",
                code="premium_required",
            )

    def check_quota(self, feature: str, current: int) -> None:
        limit = self.quota(feature)
        if current >= limit:
            raise AccessDeniedError(
                f"Limite atteinte ({limit}) pour « {FEATURE_LABELS.get(feature, feature)} ». Passez Premium pour l'illimité.",
                code="quota_exceeded",
            )

    @abstractmethod
    def quota(self, feature: str) -> int: ...

    def news_category_allowed(self, category: str) -> bool:
        return (
            self.limits.news_categories is None
            or category in self.limits.news_categories
        )

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.value,
            "label": self.label,
            "features": sorted(self.features),
            "limits": {
                "follows": None
                if self.limits.max_follows >= UNLIMITED
                else self.limits.max_follows,
                "watchlist": None
                if self.limits.max_watchlist >= UNLIMITED
                else self.limits.max_watchlist,
                "news_categories": self.limits.news_categories,
            },
        }


FEATURE_LABELS = {
    "advanced_filters": "Filtres avancés",
    "hide_titles": "Masquage automatique des titres",
    "ad_free": "Navigation sans publicité",  # [Sol]
    "follows": "Suivi d'acteurs",
    "watchlist": "Ma liste",
    "upcoming": "Prochainement",
    "seasons": "Détail des saisons",
    "actor_feed": "Fil d'actualité des acteurs suivis",
    "news_full": "Toute la presse",
    "anime_schedule": "Planning anime",
    "watch_providers": "Où regarder",
    "catalog_deep": "Catalogue étendu",
}

BASE_FEATURES = frozenset({"follows", "watchlist", "watch_providers"})
PREMIUM_FEATURES = BASE_FEATURES | frozenset(
    {
        "upcoming",
        "seasons",
        "actor_feed",
        "news_full",
        "anime_schedule",
        "catalog_deep",
        "advanced_filters",
        "hide_titles",
        "ad_free",
    }
)


class FreeAccessPolicy(AccessPolicy):
    plan = Plan.FREE
    label = "Découverte"
    features = BASE_FEATURES
    limits = Limits(
        max_follows=3,
        max_watchlist=10,
        news_sources_per_category=3,
        news_articles_per_source=5,
        news_categories=("cinema", "series"),
        catalog_pages=1,
    )

    def quota(self, feature: str) -> int:
        return {
            "follows": self.limits.max_follows,
            "watchlist": self.limits.max_watchlist,
        }.get(feature, 0)


class PremiumAccessPolicy(AccessPolicy):
    plan = Plan.PREMIUM
    label = "Premium"
    features = PREMIUM_FEATURES
    limits = Limits(
        max_follows=UNLIMITED,
        max_watchlist=UNLIMITED,
        news_sources_per_category=UNLIMITED,
        news_articles_per_source=15,
        news_categories=None,
        catalog_pages=5,
    )

    def quota(self, feature: str) -> int:
        return UNLIMITED


class AnonymousAccessPolicy(FreeAccessPolicy):
    """Visiteur non connecté : lecture seule, encore plus limité."""

    label = "Visiteur"
    features = frozenset()
    limits = Limits(
        max_follows=0,
        max_watchlist=0,
        news_sources_per_category=2,
        news_articles_per_source=3,
        news_categories=("cinema",),
        catalog_pages=1,
    )


class AccessPolicyFactory:
    @staticmethod
    def for_plan(plan: Plan | None) -> AccessPolicy:
        if plan is None:
            return AnonymousAccessPolicy()
        if plan == Plan.PREMIUM:
            return PremiumAccessPolicy()
        return FreeAccessPolicy()
