"""Adaptateur MangaDex API v5 (gratuite, sans clé) — découverte uniquement, aucun téléchargement."""

from __future__ import annotations

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.http import HttpClient

BASE_URL = "https://api.mangadex.org"
COVER_URL = "https://uploads.mangadex.org/covers"

GENRE_TAGS: dict[str, tuple[str, str]] = {
    "action": ("391b0423-d847-456f-aff0-8b0cfc03066b", "Action"),
    "aventure": ("87cc87cd-a395-47af-b27a-93258283bbc6", "Aventure"),
    "comedie": ("4d32cc48-9f00-4cca-9b5a-a839f0764984", "Comédie"),
    "drame": ("b9af3a63-f058-46de-a9a0-e0c13906197a", "Drame"),
    "fantasy": ("cdc58593-87dd-415e-bbc0-2ec27bf404cc", "Fantasy"),
    "horreur": ("cdad7e68-1419-41dd-bdce-27753074a640", "Horreur"),
    "isekai": ("ace04997-f6bd-436e-b261-779182193d3d", "Isekai"),
    "mystere": ("ee968100-4191-4968-93d3-f82d72be7e46", "Mystère"),
    "psychologique": ("3b60b75c-a2d7-4860-ab56-05f391bb889c", "Psychologique"),
    "romance": ("423e2eae-a7a2-4a8b-ac03-a8351462d71d", "Romance"),
    "sf": ("256c8bd9-4904-4360-bf4f-508a76d67183", "Science-fiction"),
    "seinen": ("seinen", "Seinen"),
    "shonen": ("shounen", "Shōnen"),
    "shojo": ("shoujo", "Shōjo"),
    "sports": ("69964a64-2f90-4d33-beeb-f3ed2875eb4c", "Sports"),
    "tranche-de-vie": ("e5301a23-ebd9-49dd-a0cb-2add944c7fe9", "Tranche de vie"),
    "thriller": ("07251805-a27e-4d59-b488-f0bfbec15168", "Thriller"),
}
DEMOGRAPHICS = {"seinen", "shounen", "shoujo", "josei"}
SORTS = {
    "popular": {"order[followedCount]": "desc"},
    "rating": {"order[rating]": "desc"},
    "new": {"order[createdAt]": "desc"},
    "updated": {"order[latestUploadedChapter]": "desc"},
    "relevance": {"order[relevance]": "desc"},
}


class MangaDexClient:
    def __init__(
        self, http: HttpClient, cache: TtlCache, cover_proxy: str = "/api/mangas/cover"
    ) -> None:
        self.http = http
        self.cache = cache
        self.cover_proxy = cover_proxy

    def _get(
        self, endpoint: str, params: list[tuple[str, str]], ttl: int = 1800
    ) -> dict:
        key = TtlCache.key(f"mangadex{endpoint}", params)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        data = self.http.get_json(f"{BASE_URL}{endpoint}", params=params) or {}
        self.cache.set(key, data, ttl)
        return data

    def _base_params(self, limit: int, offset: int) -> list[tuple[str, str]]:
        return [
            ("limit", str(max(1, min(limit, 40)))),
            ("offset", str(max(0, offset))),
            ("includes[]", "cover_art"),
            ("includes[]", "author"),
            ("availableTranslatedLanguage[]", "fr"),
            ("availableTranslatedLanguage[]", "en"),
            ("contentRating[]", "safe"),
            ("contentRating[]", "suggestive"),
            ("hasAvailableChapters", "true"),
        ]

    def _list(self, params: list[tuple[str, str]]) -> dict:
        data = self._get("/manga", params)
        results = [self._format(m) for m in data.get("data", [])]
        total = data.get("total", len(results))
        offset = data.get("offset", 0)
        return {
            "results": results,
            "total": total,
            "has_more": offset + len(results) < total,
        }

    def popular(
        self,
        limit: int = 24,
        offset: int = 0,
        sort: str = "popular",
        year: str | None = None,
    ) -> dict:
        params = self._base_params(limit, offset)
        params += list(SORTS.get(sort, SORTS["popular"]).items())
        if year and year.isdigit():
            params.append(("year", year))
        return self._list(params)

    def new_releases(self, limit: int = 24) -> dict:
        params = self._base_params(limit, 0) + list(SORTS["updated"].items())
        return self._list(params)

    def by_genre(
        self, genre_key: str, limit: int = 24, offset: int = 0, sort: str = "popular"
    ) -> dict | None:
        genre = GENRE_TAGS.get(genre_key)
        if genre is None:
            return None
        params = self._base_params(limit, offset) + list(
            SORTS.get(sort, SORTS["popular"]).items()
        )
        if genre[0] in DEMOGRAPHICS:
            params.append(("publicationDemographic[]", genre[0]))
        else:
            params.append(("includedTags[]", genre[0]))
        return self._list(params)

    def search(self, query: str, limit: int = 20) -> dict:
        params = (
            self._base_params(limit, 0)
            + [("title", query)]
            + list(SORTS["relevance"].items())
        )
        return self._list(params)

    def detail(self, manga_id: str) -> dict | None:
        data = self._get(
            f"/manga/{manga_id}",
            [
                ("includes[]", "cover_art"),
                ("includes[]", "author"),
                ("includes[]", "artist"),
            ],
            ttl=3600,
        )
        raw = data.get("data")
        if not raw:
            return None
        item = self._format(raw)
        stats = (
            self._get("/statistics/manga", [("manga[]", manga_id)], ttl=3600)
            .get("statistics", {})
            .get(manga_id, {})
        )
        item["follows"] = stats.get("follows")
        item["rating"] = (
            round((stats.get("rating") or {}).get("bayesian") or 0, 2) or item["rating"]
        )
        return item

    def chapters(self, manga_id: str, lang: str = "fr", limit: int = 12) -> list[dict]:
        params = [
            ("manga", manga_id),
            ("translatedLanguage[]", lang),
            ("order[chapter]", "desc"),
            ("limit", str(min(limit, 50))),
            ("includes[]", "scanlation_group"),
            ("contentRating[]", "safe"),
            ("contentRating[]", "suggestive"),
        ]
        data = self._get("/chapter", params, ttl=900)
        out = []
        for ch in data.get("data", []):
            attrs = ch.get("attributes", {})
            group = next(
                (
                    r["attributes"]["name"]
                    for r in ch.get("relationships", [])
                    if r.get("type") == "scanlation_group" and r.get("attributes")
                ),
                None,
            )
            out.append(
                {
                    "id": ch.get("id"),
                    "chapter": attrs.get("chapter"),
                    "title": attrs.get("title"),
                    "lang": attrs.get("translatedLanguage"),
                    "pages": attrs.get("pages"),
                    "date": attrs.get("readableAt"),
                    "group": group,
                    "url": f"https://mangadex.org/chapter/{ch.get('id')}",
                }
            )
        return out

    @staticmethod
    def genres() -> list[dict]:
        return [{"key": k, "label": v[1]} for k, v in GENRE_TAGS.items()]

    def cover_bytes(self, url: str) -> tuple[bytes, str]:
        if not url.startswith(COVER_URL):
            raise ValueError("URL de couverture non autorisée")
        return self.http.get_bytes(
            url, headers={"Referer": "https://mangadex.org/", "Accept": "image/*"}
        )

    # ---- normalisation -------------------------------------------------
    def _format(self, raw: dict) -> dict:
        attrs = raw.get("attributes", {})
        rels = raw.get("relationships", [])
        cover_file = next(
            (
                r["attributes"]["fileName"]
                for r in rels
                if r.get("type") == "cover_art" and r.get("attributes")
            ),
            None,
        )
        authors = [
            r["attributes"]["name"]
            for r in rels
            if r.get("type") in ("author", "artist") and r.get("attributes")
        ]
        titles = attrs.get("title", {}) or {}
        alt = attrs.get("altTitles", []) or []
        title = (
            titles.get("fr")
            or next((t["fr"] for t in alt if "fr" in t), None)
            or titles.get("en")
            or next(iter(titles.values()), "Sans titre")
        )
        desc = attrs.get("description", {}) or {}
        cover = f"{COVER_URL}/{raw['id']}/{cover_file}.512.jpg" if cover_file else None
        return {
            "id": raw.get("id"),
            "media_type": "manga",
            "title": title,
            "author": ", ".join(dict.fromkeys(authors)) or None,
            "year": str(attrs.get("year") or ""),
            "cover": f"{self.cover_proxy}?url={cover}" if cover else None,
            "overview": (desc.get("fr") or desc.get("en") or "")[:600],
            "genres": [
                t["attributes"]["name"].get("en")
                for t in attrs.get("tags", [])
                if t.get("attributes")
            ][:6],
            "status": attrs.get("status"),
            "demographic": attrs.get("publicationDemographic"),
            "rating": 0,
            "has_french": "fr" in (attrs.get("availableTranslatedLanguages") or []),
            "read_urls": {
                "mangadex": f"https://mangadex.org/title/{raw.get('id')}",
                "mangaplus": f"https://mangaplus.shueisha.co.jp/search_result?keyword={title}",
            },
        }
