"""Façade catalogue : un point d'entrée pour le web, qui applique la politique d'accès.

Le web ne parle jamais directement aux clients d'API : il demande au
``CatalogService`` avec une ``AccessPolicy``, qui décide de la profondeur
(pages, catégories, sources) accordée au visiteur.
"""

from __future__ import annotations

from yumnews.catalog.anilist.client import AnimeScheduleClient
from yumnews.catalog.mangadex.client import MangaDexClient
from yumnews.catalog.news.client import NewsClient
from yumnews.catalog.tmdb.client import TmdbClient
from yumnews.services.access_policy import AccessPolicy
from yumnews.services.errors import NotFoundError, ValidationError


class CatalogService:
    def __init__(
        self,
        tmdb: TmdbClient,
        mangadex: MangaDexClient,
        news: NewsClient,
        anilist: AnimeScheduleClient,
    ) -> None:
        self.tmdb = tmdb
        self.mangadex = mangadex
        self.press = news  # « news » est réservé à la méthode publique
        self.anilist = anilist

    def landing_visuals(self) -> list[dict]:
        """[Sol] Sélection publique limitée aux visuels de présentation."""
        return self.tmdb.landing_visuals()

    # ---- accueil -------------------------------------------------------
    def home(self, policy: AccessPolicy, preferences: dict | None = None) -> dict:
        """[Sol] Les rubriques masquées ne déclenchent aucun appel externe."""
        from yumnews.services.preference_service import DEFAULTS

        prefs = preferences or DEFAULTS
        sections = set(prefs["sections"])
        hero = self.tmdb.hero() if sections & {"movies", "series"} else []
        return {
            "hero": [
                i
                for i in hero
                if ("series" if i.get("media_type") == "tv" else "movies") in sections
            ],
            "movies_trending": self.tmdb.trending_movies()[:20]
            if "movies" in sections
            else [],
            "series_trending": self.tmdb.trending_series()[:20]
            if "series" in sections
            else [],
            "now_playing": self.tmdb.now_playing()[:20] if "movies" in sections else [],
            "mangas_new": self.mangadex.new_releases(limit=20)["results"]
            if "mangas" in sections
            else [],
            "people": self.tmdb.featured_people() if "people" in sections else [],
            "headlines": self.personal_headlines(policy, prefs)
            if "news" in sections
            else [],
        }

    def personal_headlines(self, policy: AccessPolicy, preferences: dict) -> list[dict]:
        from yumnews.catalog.news.sources import SOURCES_BY_KEY

        articles = []
        selected = preferences["news_sources"]
        for category in self._news_categories(policy, preferences["news_categories"]):
            if selected:
                keys = [k for k in selected if SOURCES_BY_KEY[k].category == category]
                for key in keys[: policy.limits.news_sources_per_category]:
                    articles.extend(
                        self.press.feed(
                            key, limit=policy.limits.news_articles_per_source
                        )
                        or []
                    )
            else:
                articles.extend(self.news(policy, category))
        unique = {a.get("url") or a.get("title"): a for a in articles}
        return sorted(unique.values(), key=lambda a: a.get("date") or "", reverse=True)[
            :24
        ]

    # ---- films / séries ------------------------------------------------
    def movies(
        self, policy: AccessPolicy, list_key: str, sort: str = "popularity"
    ) -> list[dict]:
        pages = policy.limits.catalog_pages
        table = {
            "trending": lambda: self.tmdb.trending_movies(pages=pages),
            "now_playing": lambda: self.tmdb.now_playing(pages=pages),
            "upcoming": lambda: self._premium(
                policy, "upcoming", lambda: self.tmdb.upcoming_movies(pages=pages + 1)
            ),
            "popular": lambda: self.tmdb.popular_movies(pages=pages),
            "top_rated": lambda: self.tmdb.top_rated_movies(pages=pages),
        }
        if list_key in table:
            return table[list_key]()
        items = self.tmdb.movies_by_genre(list_key, sort, pages=pages)
        if items is None:
            raise NotFoundError("Liste inconnue.")
        return items

    def series(
        self, policy: AccessPolicy, list_key: str, sort: str = "popularity"
    ) -> list[dict]:
        pages = policy.limits.catalog_pages
        table = {
            "trending": lambda: self.tmdb.trending_series(pages=pages),
            "airing": lambda: self.tmdb.airing_today(pages=pages),
            "top_rated": lambda: self.tmdb.top_rated_series(pages=pages),
            "upcoming": lambda: self._premium(
                policy, "upcoming", lambda: self.tmdb.upcoming_series(pages=pages + 1)
            ),
        }
        if list_key in table:
            return table[list_key]()
        if list_key.startswith("platform:"):
            items = self.tmdb.series_by_platform(list_key.split(":", 1)[1], pages=pages)
        else:
            items = self.tmdb.series_by_genre(list_key, sort, pages=pages)
        if items is None:
            raise NotFoundError("Liste inconnue.")
        return items

    def upcoming(self, policy: AccessPolicy) -> dict:
        policy.require("upcoming")
        return {
            "movies": self.tmdb.upcoming_movies(pages=3),
            "series": self.tmdb.upcoming_series(pages=3),
        }

    def detail(self, policy: AccessPolicy, media_type: str, media_id: int) -> dict:
        data = self.tmdb.detail(media_type, media_id)
        if data is None:
            raise NotFoundError("Titre introuvable.")
        if not policy.can("watch_providers"):
            data["watch"]["locked"] = True
            data["watch"]["offers"] = data["watch"]["offers"][:1]
        return data

    def seasons(self, policy: AccessPolicy, tv_id: int) -> list[dict]:
        policy.require("seasons")
        return self.tmdb.seasons(tv_id)

    def search(self, query: str) -> dict:
        query = (query or "").strip()
        if len(query) < 2:
            raise ValidationError("Recherche trop courte.")
        return {
            "query": query,
            "results": self.tmdb.search(query),
            "mangas": self.mangadex.search(query, limit=8)["results"],
        }

    # ---- personnes ------------------------------------------------------
    def people(self, page: int = 1) -> dict:
        return self.tmdb.popular_people(page)

    def person(self, person_id: int) -> dict:
        data = self.tmdb.person(person_id)
        if data is None:
            raise NotFoundError("Personne introuvable.")
        return data

    def person_feed(self, policy: AccessPolicy, person_ids: list[int]) -> dict:
        if not person_ids:
            return {"upcoming": [], "recent": []}
        feed = self.tmdb.person_feed(person_ids)
        if not policy.can("actor_feed"):
            feed = {
                "upcoming": feed["upcoming"][:5],
                "recent": feed["recent"][:5],
                "locked": True,
            }
        return feed

    # ---- mangas ---------------------------------------------------------
    def mangas(
        self,
        policy: AccessPolicy,
        list_key: str,
        sort: str = "popular",
        offset: int = 0,
        year: str | None = None,
    ) -> dict:
        limit = 40 if policy.can("catalog_deep") else 24
        if list_key == "popular":
            return self.mangadex.popular(
                limit=limit, offset=offset, sort=sort, year=year
            )
        if list_key == "new":
            return self.mangadex.new_releases(limit=limit)
        data = self.mangadex.by_genre(list_key, limit=limit, offset=offset, sort=sort)
        if data is None:
            raise NotFoundError("Genre inconnu.")
        return data

    def manga(self, manga_id: str) -> dict:
        data = self.mangadex.detail(manga_id)
        if data is None:
            raise NotFoundError("Manga introuvable.")
        data["chapters"] = self.mangadex.chapters(
            manga_id, "fr"
        ) or self.mangadex.chapters(manga_id, "en")
        return data

    def anime_schedule(self, policy: AccessPolicy) -> list[dict]:
        episodes = self.anilist.weekly_schedule()
        if not policy.can("anime_schedule"):
            return episodes[:8]
        return episodes

    # ---- presse ---------------------------------------------------------
    def news_categories(self, policy: AccessPolicy) -> list[dict]:
        return [
            {**c, "locked": not policy.news_category_allowed(c["key"])}
            for c in self.press.categories()
        ]

    def news(
        self, policy: AccessPolicy, category: str, source: str | None = None
    ) -> list[dict]:
        if category not in {c["key"] for c in self.press.categories()}:
            raise NotFoundError("Catégorie inconnue.")
        if not policy.news_category_allowed(category):
            policy.require("news_full")
        if source:
            # [Sol] Une source doit appartenir à la catégorie demandée.
            from yumnews.catalog.news.sources import SOURCES_BY_KEY

            if (
                source not in SOURCES_BY_KEY
                or SOURCES_BY_KEY[source].category != category
            ):
                raise NotFoundError("Source inconnue pour cette catégorie.")
            articles = self.press.feed(
                source, limit=policy.limits.news_articles_per_source
            )
            if articles is None:
                raise NotFoundError("Source inconnue.")
            return articles
        return (
            self.press.category(
                category,
                max_sources=policy.limits.news_sources_per_category,
                per_source=policy.limits.news_articles_per_source,
            )
            or []
        )

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _premium(policy: AccessPolicy, feature: str, loader):
        policy.require(feature)
        return loader()

    @staticmethod
    def _news_categories(policy: AccessPolicy, wanted: list[str]) -> list[str]:
        return [c for c in wanted if policy.news_category_allowed(c)]
