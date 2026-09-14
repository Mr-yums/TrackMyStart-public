"""Planning des épisodes anime de la semaine.

Deux fournisseurs gratuits et sans clé, essayés dans l'ordre (pattern Chain of
Responsibility) : AniList (GraphQL, précis à la minute) puis Jikan/MyAnimeList
(REST, jour + heure de diffusion). Si les deux échouent, liste vide mise en
cache 5 minutes pour ne pas marteler des API en panne.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.http import ApiUnavailable, HttpClient

log = logging.getLogger(__name__)

ANILIST_ENDPOINT = "https://graphql.anilist.co"
ANILIST_QUERY = """
query ($page: Int, $start: Int, $end: Int) {
  Page(page: $page, perPage: 50) {
    pageInfo { hasNextPage }
    airingSchedules(airingAt_greater: $start, airingAt_lesser: $end, sort: TIME) {
      airingAt episode
      media {
        id isAdult format popularity
        title { romaji english native }
        coverImage { large color }
        siteUrl
        externalLinks { site url type }
      }
    }
  }
}
"""
JIKAN_ENDPOINT = "https://api.jikan.moe/v4/schedules"
JST = timezone(timedelta(hours=9))
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


class AniListProvider:
    name = "anilist"

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def fetch(self, days: int, min_popularity: int) -> list[dict]:
        now = int(time.time())
        start, end = now - 12 * 3600, now + days * 86400
        episodes: list[dict] = []
        for page in range(1, 6):
            data = self.http.post_json(
                ANILIST_ENDPOINT,
                {
                    "query": ANILIST_QUERY,
                    "variables": {"page": page, "start": start, "end": end},
                },
            )
            page_data = (data.get("data") or {}).get("Page") or {}
            for sched in page_data.get("airingSchedules", []):
                media = sched.get("media") or {}
                if (
                    media.get("isAdult")
                    or (media.get("popularity") or 0) < min_popularity
                ):
                    continue
                title = media.get("title") or {}
                episodes.append(
                    {
                        "id": media.get("id"),
                        "media_type": "anime",
                        "title": title.get("english") or title.get("romaji"),
                        "episode": sched.get("episode"),
                        "airing_at": sched.get("airingAt"),
                        "cover": (media.get("coverImage") or {}).get("large"),
                        "color": (media.get("coverImage") or {}).get("color"),
                        "format": media.get("format"),
                        "url": media.get("siteUrl"),
                        "streaming": [
                            {"site": l["site"], "url": l["url"]}
                            for l in media.get("externalLinks", []) or []
                            if l.get("type") == "STREAMING"
                        ][:4],
                        "popularity": media.get("popularity") or 0,
                        "source": self.name,
                    }
                )
            if not (page_data.get("pageInfo") or {}).get("hasNextPage"):
                break
        return episodes


class JikanProvider:
    """MyAnimeList via Jikan : un appel par jour de la semaine, heure JST convertie en UTC."""

    name = "jikan"

    def __init__(self, http: HttpClient) -> None:
        self.http = http

    def fetch(self, days: int, min_popularity: int) -> list[dict]:
        today = datetime.now(JST).date()
        episodes: list[dict] = []
        for offset in range(min(days, 7)):
            day = today + timedelta(days=offset)
            data = (
                self.http.get_json(
                    JIKAN_ENDPOINT,
                    params={"filter": DAYS[day.weekday()], "sfw": "true", "limit": 25},
                )
                or {}
            )
            for anime in data.get("data", []):
                members = anime.get("members") or 0
                if members < min_popularity:
                    continue
                broadcast = anime.get("broadcast") or {}
                hhmm = (broadcast.get("time") or "00:00").split(":")
                airing = datetime(
                    day.year, day.month, day.day, int(hhmm[0]), int(hhmm[1]), tzinfo=JST
                )
                images = (anime.get("images") or {}).get("jpg") or {}
                episodes.append(
                    {
                        "id": anime.get("mal_id"),
                        "media_type": "anime",
                        "title": anime.get("title_english") or anime.get("title"),
                        "episode": None,
                        "airing_at": int(airing.timestamp()),
                        "cover": images.get("large_image_url")
                        or images.get("image_url"),
                        "color": None,
                        "format": anime.get("type"),
                        "url": anime.get("url"),
                        "streaming": [],
                        "popularity": members,
                        "source": self.name,
                    }
                )
            time.sleep(0.4)  # Jikan : 3 req/s max
        episodes.sort(key=lambda e: e["airing_at"])
        return episodes


class AnimeScheduleClient:
    def __init__(
        self,
        http: HttpClient,
        cache: TtlCache,
        ttl: int = 3600,
        providers: list | None = None,
    ) -> None:
        self.cache = cache
        self.ttl = ttl
        self.providers = providers or [AniListProvider(http), JikanProvider(http)]

    def weekly_schedule(self, days: int = 7, min_popularity: int = 3000) -> list[dict]:
        key = f"anime:schedule:{days}:{min_popularity}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        for provider in self.providers:
            try:
                episodes = provider.fetch(days, min_popularity)
            except (ApiUnavailable, ValueError, KeyError, TypeError) as exc:
                log.warning("Planning anime : %s indisponible (%s)", provider.name, exc)
                continue
            if episodes:
                self.cache.set(key, episodes, ttl=self.ttl)
                return episodes
        self.cache.set(key, [], ttl=300)
        return []


# Compatibilité : ancien nom
AniListClient = AnimeScheduleClient
