"""Adaptateur TMDB (API v3, gratuite). Toutes les réponses passent par le cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.http import ApiUnavailable, HttpClient
from yumnews.catalog.tmdb import normalizer as norm
from yumnews.catalog.tmdb.constants import (
    MOVIE_GENRES,
    ORIGIN_COUNTRIES,
    PLATFORMS,
    TV_GENRES,
    PROVIDER_TO_PLATFORM,
)

BASE_URL = "https://api.themoviedb.org/3"
FEATURED_PEOPLE = (
    "Timothée Chalamet",
    "Zendaya",
    "Léa Seydoux",
    "Pedro Pascal",
    "Florence Pugh",
    "Omar Sy",
    "Cillian Murphy",
    "Margot Robbie",
    "Denis Villeneuve",
    "Anya Taylor-Joy",
)


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        http: HttpClient,
        cache: TtlCache,
        language: str = "fr-FR",
        region: str = "FR",
    ) -> None:
        self.api_key = api_key
        self.http = http
        self.cache = cache
        self.language = language
        self.region = region

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    # ---- bas niveau --------------------------------------------------
    def _get(
        self, endpoint: str, params: dict | None = None, ttl: int | None = None
    ) -> dict | None:
        params = {"api_key": self.api_key, "language": self.language, **(params or {})}
        key = TtlCache.key(
            f"tmdb{endpoint}", {k: v for k, v in params.items() if k != "api_key"}
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        data = self.http.get_json(f"{BASE_URL}{endpoint}", params=params)
        if data is not None:
            self.cache.set(key, data, ttl)
        return data

    def _pages(self, endpoint: str, params: dict, pages: int) -> list[dict]:
        """Pages 1..n en parallèle, dédoublonnées, ordre conservé."""

        def fetch(page: int) -> list[dict]:
            try:
                data = self._get(endpoint, {**params, "page": page}) or {}
            except ApiUnavailable:
                return []
            return data.get("results", [])

        with ThreadPoolExecutor(max_workers=min(pages, 5)) as pool:
            batches = list(pool.map(fetch, range(1, pages + 1)))
        seen: set[int] = set()
        out: list[dict] = []
        for batch in batches:
            for raw in batch:
                if raw.get("id") not in seen:
                    seen.add(raw["id"])
                    out.append(raw)
        return out

    @staticmethod
    def _keep(raw: dict) -> bool:
        """Écarte les entrées sans visuel ni popularité (bruit TMDB)."""
        if not raw.get("poster_path"):
            return False
        lang = raw.get("original_language")
        votes = raw.get("vote_count") or 0
        if lang in ("en", "fr"):
            return True
        if lang == "ja":
            return votes >= (100 if 16 in (raw.get("genre_ids") or []) else 300)
        return votes >= 200

    def _items(
        self,
        raws: list[dict],
        media_type: str | None = None,
        limit: int | None = None,
        strict: bool = True,
    ) -> list[dict]:
        items = [
            norm.media_item(r, media_type)
            for r in raws
            if (not strict or self._keep(r))
        ]
        return items[:limit] if limit else items

    # ---- listes films -------------------------------------------------
    def trending_movies(self, window: str = "week", pages: int = 1) -> list[dict]:
        return self._items(self._pages(f"/trending/movie/{window}", {}, pages), "movie")

    def now_playing(self, pages: int = 1) -> list[dict]:
        return self._items(
            self._pages("/movie/now_playing", {"region": self.region}, pages), "movie"
        )

    def upcoming_movies(self, pages: int = 2) -> list[dict]:
        today = date.today().isoformat()
        raws = self._pages("/movie/upcoming", {"region": self.region}, pages)
        items = self._items(
            [r for r in raws if (r.get("release_date") or "") >= today],
            "movie",
            strict=False,
        )
        return sorted(items, key=lambda i: i["date"] or "9999")

    def popular_movies(self, pages: int = 1) -> list[dict]:
        return self._items(
            self._pages("/movie/popular", {"region": self.region}, pages), "movie"
        )

    def top_rated_movies(self, pages: int = 1) -> list[dict]:
        return self._items(
            self._pages("/movie/top_rated", {"region": self.region}, pages), "movie"
        )

    def movies_by_genre(
        self, genre_key: str, sort: str = "popularity", pages: int = 1
    ) -> list[dict] | None:
        genre = MOVIE_GENRES.get(genre_key)
        if genre is None:
            return None
        params = {
            "with_genres": genre[0],
            "sort_by": "vote_average.desc" if sort == "rating" else "popularity.desc",
            "vote_count.gte": 200 if sort == "rating" else 50,
            "region": self.region,
            "with_origin_country": ORIGIN_COUNTRIES,
        }
        return self._items(self._pages("/discover/movie", params, pages), "movie")

    # ---- listes séries ------------------------------------------------
    def trending_series(self, window: str = "week", pages: int = 1) -> list[dict]:
        return self._items(self._pages(f"/trending/tv/{window}", {}, pages), "tv")

    def airing_today(self, pages: int = 1) -> list[dict]:
        return self._items(self._pages("/tv/on_the_air", {}, pages), "tv")

    def top_rated_series(self, pages: int = 1) -> list[dict]:
        return self._items(self._pages("/tv/top_rated", {}, pages), "tv")

    def series_by_genre(
        self, genre_key: str, sort: str = "popularity", pages: int = 1
    ) -> list[dict] | None:
        genre = TV_GENRES.get(genre_key)
        if genre is None:
            return None
        params = {
            "with_genres": genre[0],
            "sort_by": "vote_average.desc" if sort == "rating" else "popularity.desc",
            "vote_count.gte": 100 if sort == "rating" else 20,
            "with_origin_country": ORIGIN_COUNTRIES,
        }
        return self._items(self._pages("/discover/tv", params, pages), "tv")

    def series_by_platform(
        self, platform_key: str, pages: int = 1
    ) -> list[dict] | None:
        platform = PLATFORMS.get(platform_key)
        if platform is None or not platform.tmdb_provider_ids:
            return None
        params = {
            "with_watch_providers": "|".join(
                str(i) for i in platform.tmdb_provider_ids
            ),
            "watch_region": self.region,
            "sort_by": "popularity.desc",
        }
        return self._items(self._pages("/discover/tv", params, pages), "tv")

    def upcoming_series(self, pages: int = 2) -> list[dict]:
        today = date.today()
        params = {
            "first_air_date.gte": today.isoformat(),
            "first_air_date.lte": (today + timedelta(days=120)).isoformat(),
            "sort_by": "popularity.desc",
            "with_origin_country": ORIGIN_COUNTRIES,
        }
        items = self._items(
            self._pages("/discover/tv", params, pages), "tv", strict=False
        )
        return sorted(items, key=lambda i: i["date"] or "9999")

    def landing_visuals(self) -> list[dict]:
        """[Sol] Visuels récents France ; disponibilité Netflix, pas date d'ajout."""
        if not self.configured:
            return []
        today = date.today()
        params = {
            "watch_region": self.region,
            "with_watch_providers": "8",
            "with_watch_monetization_types": "flatrate",
            "include_adult": "false",
            "first_air_date.gte": (today - timedelta(days=120)).isoformat(),
            "first_air_date.lte": today.isoformat(),
            "sort_by": "popularity.desc",
        }

        def cinema():
            return self._pages("/movie/now_playing", {"region": self.region}, 1)

        def netflix():
            return self._pages("/discover/tv", params, 1)

        with ThreadPoolExecutor(max_workers=2) as pool:
            batches = list(pool.map(lambda loader: loader(), (cinema, netflix)))
        groups = []
        for raws, kind, label in zip(
            batches,
            ("movie", "tv"),
            ("En salles · France", "Netflix · séries récentes"),
        ):
            items = []
            for raw in raws:
                if raw.get("adult") or not raw.get("backdrop_path"):
                    continue
                item = norm.media_item(raw, kind)
                if not item["title"] or not item["id"]:
                    continue
                items.append(
                    {
                        "title": item["title"],
                        "backdrop": item["backdrop"],
                        "label": label,
                        "source_url": f"https://www.themoviedb.org/{kind}/{item['id']}",
                    }
                )
                if len(items) == 4:
                    break
            groups.append(items)
        # Alterner cinéma / Netflix ; chaque catégorie peut manquer indépendamment.
        return [
            group[index] for index in range(4) for group in groups if index < len(group)
        ]

    # ---- transversal --------------------------------------------------
    def hero(self, limit: int = 6) -> list[dict]:
        raws = (self._get("/trending/all/week") or {}).get("results", [])
        items = []
        for raw in raws:
            if raw.get("media_type") not in ("movie", "tv") or not raw.get(
                "backdrop_path"
            ):
                continue
            item = norm.media_item(raw)
            item["backdrop"] = norm.image(raw.get("backdrop_path"), "original")
            items.append(item)
            if len(items) >= limit:
                break
        return items

    def search(self, query: str, limit: int = 24) -> list[dict]:
        data = (
            self._get(
                "/search/multi", {"query": query, "include_adult": "false"}, ttl=600
            )
            or {}
        )
        out = []
        for raw in data.get("results", []):
            if raw.get("media_type") == "person":
                if raw.get("profile_path"):
                    out.append({**norm.person_item(raw), "media_type": "person"})
            elif raw.get("media_type") in ("movie", "tv") and raw.get("poster_path"):
                out.append(norm.media_item(raw))
        return out[:limit]

    def detail(self, media_type: str, media_id: int) -> dict | None:
        if media_type not in ("movie", "tv"):
            return None
        raw = self._get(
            f"/{media_type}/{media_id}",
            {"append_to_response": "videos,credits,watch/providers"},
        )
        return norm.detail(raw, media_type, self.region) if raw else None

    def filter_metadata(self, media_type: str, media_id: int) -> dict:
        """[Sol] Pays de production réel et durée, sans charger casting ni vidéos."""
        raw = self._get(f"/{media_type}/{media_id}") or {}
        runtime = (
            raw.get("runtime")
            if media_type == "movie"
            else next((v for v in raw.get("episode_run_time", []) if v), None)
        )
        return {
            "production_countries": [
                c["iso_3166_1"]
                for c in raw.get("production_countries", [])
                if c.get("iso_3166_1")
            ],
            "runtime": runtime or None,
        }

    def seasons(self, tv_id: int) -> list[dict]:
        show = self._get(f"/tv/{tv_id}") or {}
        numbers = [
            s["season_number"]
            for s in show.get("seasons", [])
            if s.get("season_number", 0) > 0
        ]

        def fetch(n: int) -> dict | None:
            try:
                raw = self._get(f"/tv/{tv_id}/season/{n}")
            except ApiUnavailable:
                return None
            return norm.season(raw) if raw else None

        with ThreadPoolExecutor(max_workers=4) as pool:
            seasons = [s for s in pool.map(fetch, numbers[:30]) if s]
        return seasons

    # ---- personnes ----------------------------------------------------
    def popular_people(self, page: int = 1) -> dict:
        data = self._get("/person/popular", {"page": max(1, min(page, 50))}) or {}
        people = [
            norm.person_item(p)
            for p in data.get("results", [])
            if p.get("profile_path")
        ]
        return {
            "results": people,
            "page": data.get("page", page),
            "total_pages": min(data.get("total_pages", 1), 50),
        }

    def featured_people(self) -> list[dict]:
        def fetch(name: str) -> dict | None:
            try:
                data = self._get("/search/person", {"query": name}, ttl=86400) or {}
            except ApiUnavailable:
                return None
            hits = [p for p in data.get("results", []) if p.get("profile_path")]
            return norm.person_item(hits[0]) if hits else None

        with ThreadPoolExecutor(max_workers=5) as pool:
            return [p for p in pool.map(fetch, FEATURED_PEOPLE) if p]

    def person(self, person_id: int) -> dict | None:
        raw = self._get(
            f"/person/{person_id}", {"append_to_response": "combined_credits"}
        )
        if not raw:
            return None
        if not raw.get("biography") and self.language != "en-US":
            # TMDB ne traduit pas toutes les biographies : repli sur l'anglais.
            fallback = (
                self._get(f"/person/{person_id}", {"language": "en-US"}, ttl=86400)
                or {}
            )
            raw = {
                **raw,
                "biography": fallback.get("biography") or "",
                "biography_lang": "en" if fallback.get("biography") else None,
            }
        return norm.person_detail(raw)

    def person_feed(
        self, person_ids: list[int], days_back: int = 120, days_ahead: int = 365
    ) -> dict:
        """Sorties récentes et à venir des personnes suivies (fil d'actualité)."""
        today = date.today()
        lo, hi = (
            (today - timedelta(days=days_back)).isoformat(),
            (today + timedelta(days=days_ahead)).isoformat(),
        )

        def fetch(pid: int) -> list[dict]:
            try:
                data = self.person(pid)
            except ApiUnavailable:
                return []
            if not data:
                return []
            out = []
            for credit in data["credits"]:
                if credit["date"] and lo <= credit["date"] <= hi:
                    out.append(
                        {
                            **credit,
                            "person": {
                                "id": data["id"],
                                "name": data["name"],
                                "profile": data["portrait"],
                            },
                        }
                    )
            return out

        with ThreadPoolExecutor(max_workers=5) as pool:
            entries = [e for batch in pool.map(fetch, person_ids[:40]) for e in batch]
        seen: set[tuple[str, int]] = set()
        unique = []
        for e in entries:
            key = (e["media_type"], e["id"])
            if key not in seen:
                seen.add(key)
                unique.append(e)
        cutoff = today.isoformat()
        upcoming = sorted(
            [e for e in unique if e["date"] >= cutoff], key=lambda e: e["date"]
        )
        recent = sorted(
            [e for e in unique if e["date"] < cutoff],
            key=lambda e: e["date"],
            reverse=True,
        )
        return {"upcoming": upcoming[:40], "recent": recent[:40]}

    def genres(self) -> dict:
        return {
            "movie": [
                {"key": k, "id": v[0], "label": v[1]} for k, v in MOVIE_GENRES.items()
            ],
            "tv": [{"key": k, "id": v[0], "label": v[1]} for k, v in TV_GENRES.items()],
        }

    @staticmethod
    def platforms() -> list[dict]:
        return [
            {
                "key": p.key,
                "name": p.name,
                "color": p.color,
                "home_url": p.home_url,
                "filterable": bool(p.tmdb_provider_ids),
            }
            for p in PLATFORMS.values()
        ]
