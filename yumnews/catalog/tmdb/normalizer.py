"""Transforme les réponses brutes TMDB en objets plats et stables pour le front."""

from __future__ import annotations

from yumnews.catalog.tmdb.constants import (
    NETWORK_TO_PLATFORM,
    PROVIDER_TO_PLATFORM,
    Platform,
)

IMAGE_BASE = "https://image.tmdb.org/t/p"


def image(path: str | None, size: str) -> str | None:
    return f"{IMAGE_BASE}/{size}{path}" if path else None


def year_of(date: str | None) -> str:
    return (date or "")[:4]


def media_item(raw: dict, media_type: str | None = None) -> dict:
    kind = (
        media_type
        or raw.get("media_type")
        or (
            "tv"
            if "first_air_date" in raw or "name" in raw and "title" not in raw
            else "movie"
        )
    )
    is_tv = kind == "tv"
    date = raw.get("first_air_date") if is_tv else raw.get("release_date")
    return {
        "id": raw.get("id"),
        "media_type": kind,
        "title": raw.get("name") if is_tv else raw.get("title"),
        "original_title": raw.get("original_name")
        if is_tv
        else raw.get("original_title"),
        "year": year_of(date),
        "date": date,
        "poster": image(raw.get("poster_path"), "w500"),
        "backdrop": image(raw.get("backdrop_path"), "w1280"),
        "rating": round(raw.get("vote_average") or 0, 1),
        "votes": raw.get("vote_count") or 0,
        "overview": raw.get("overview") or "",
        "genre_ids": raw.get("genre_ids") or [g["id"] for g in raw.get("genres", [])],
        "popularity": raw.get("popularity") or 0,
    }


def person_item(raw: dict) -> dict:
    known_for = [
        media_item(k)
        for k in raw.get("known_for", [])
        if k.get("media_type") in ("movie", "tv")
    ]
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "profile": image(raw.get("profile_path"), "w342"),
        "department": raw.get("known_for_department"),
        "popularity": raw.get("popularity") or 0,
        "known_for": [
            {
                "id": k["id"],
                "media_type": k["media_type"],
                "title": k["title"],
                "poster": k["poster"],
            }
            for k in known_for[:3]
        ],
    }


def platform_dict(platform: Platform, title: str) -> dict:
    return {
        "key": platform.key,
        "name": platform.name,
        "color": platform.color,
        "url": platform.search_link(title) if title else platform.home_url,
    }


def watch_offers(raw_providers: dict | None, region: str, title: str) -> dict:
    """Normalise ``watch/providers`` : plateformes officielles + lien JustWatch fourni par TMDB."""
    results = (raw_providers or {}).get("results", {}) if raw_providers else {}
    local = results.get(region) or {}
    kinds = {
        "flatrate": "Abonnement",
        "free": "Gratuit",
        "ads": "Gratuit (pub)",
        "rent": "Location",
        "buy": "Achat",
    }
    offers: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for kind, label in kinds.items():
        for provider in local.get(kind, []) or []:
            platform = PROVIDER_TO_PLATFORM.get(provider.get("provider_id"))
            name = platform.name if platform else provider.get("provider_name")
            key = (name or "", label)
            if key in seen:
                continue
            seen.add(key)
            offers.append(
                {
                    "kind": kind,
                    "kind_label": label,
                    "name": name,
                    "logo": image(provider.get("logo_path"), "w92"),
                    "color": platform.color if platform else "#444",
                    "url": platform.search_link(title)
                    if platform
                    else local.get("link"),
                    "official": platform is not None,
                }
            )
    return {"offers": offers, "justwatch": local.get("link"), "region": region}


def platform_from_networks(raw: dict, title: str) -> dict | None:
    for network in raw.get("networks", []) or []:
        platform = NETWORK_TO_PLATFORM.get(network.get("id"))
        if platform:
            return platform_dict(platform, title)
    return None


def detail(raw: dict, media_type: str, region: str) -> dict:
    base = media_item(raw, media_type)
    videos = (raw.get("videos") or {}).get("results", [])
    credits = raw.get("credits") or {}
    cast = [
        {
            "id": c.get("id"),
            "name": c.get("name"),
            "character": c.get("character"),
            "profile": image(c.get("profile_path"), "w185"),
            "department": c.get("known_for_department"),
        }
        for c in credits.get("cast", [])[:16]
    ]
    if media_type == "movie":
        directors = [
            {
                "id": c["id"],
                "name": c["name"],
                "profile": image(c.get("profile_path"), "w185"),
            }
            for c in credits.get("crew", [])
            if c.get("job") == "Director"
        ]
        runtime = raw.get("runtime")
    else:
        directors = [
            {
                "id": c["id"],
                "name": c["name"],
                "profile": image(c.get("profile_path"), "w185"),
            }
            for c in raw.get("created_by", [])
        ]
        runtime = (raw.get("episode_run_time") or [None])[0]
    base.update(
        {
            "backdrop": image(raw.get("backdrop_path"), "original"),
            "tagline": raw.get("tagline") or "",
            "genres": [g["name"] for g in raw.get("genres", [])],
            "runtime": runtime,
            "status": raw.get("status"),
            "nb_seasons": raw.get("number_of_seasons"),
            "nb_episodes": raw.get("number_of_episodes"),
            "trailer_url": _trailer(videos),
            "cast": cast,
            "directors": directors,
            "watch": watch_offers(
                raw.get("watch/providers"), region, base["title"] or ""
            ),
            "network_platform": platform_from_networks(raw, base["title"] or "")
            if media_type == "tv"
            else None,
            "homepage": raw.get("homepage") or None,
        }
    )
    return base


def _trailer(videos: list[dict]) -> str | None:
    yt = [v for v in videos if v.get("site") == "YouTube"]
    ranked = sorted(
        yt,
        key=lambda v: (
            v.get("type") != "Trailer",
            v.get("iso_639_1") != "fr",
            v.get("type") != "Teaser",
        ),
    )
    if not ranked:
        return None
    return f"https://www.youtube.com/embed/{ranked[0]['key']}?rel=0&modestbranding=1"


def season(raw: dict) -> dict:
    return {
        "season_number": raw.get("season_number"),
        "name": raw.get("name"),
        "overview": raw.get("overview") or "",
        "air_date": raw.get("air_date"),
        "poster": image(raw.get("poster_path"), "w342"),
        "episodes": [
            {
                "episode_number": e.get("episode_number"),
                "name": e.get("name"),
                "overview": (e.get("overview") or "")[:220],
                "air_date": e.get("air_date"),
                "still": image(e.get("still_path"), "w300"),
                "runtime": e.get("runtime"),
                "rating": round(e.get("vote_average") or 0, 1),
            }
            for e in raw.get("episodes", [])
        ],
    }


def person_detail(raw: dict) -> dict:
    credits = raw.get("combined_credits") or {}
    entries: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for c in credits.get("cast", []) + credits.get("crew", []):
        kind = c.get("media_type")
        if kind not in ("movie", "tv") or (kind, c["id"]) in seen:
            continue
        seen.add((kind, c["id"]))
        item = media_item(c, kind)
        item["character"] = c.get("character") or c.get("job")
        entries.append(item)
    entries.sort(key=lambda e: e["date"] or "", reverse=True)
    return {
        "id": raw.get("id"),
        "name": raw.get("name"),
        "portrait": image(raw.get("profile_path"), "h632"),
        "biography": raw.get("biography") or "",
        "biography_lang": raw.get("biography_lang") or "fr",
        "birthday": raw.get("birthday"),
        "deathday": raw.get("deathday"),
        "birthplace": raw.get("place_of_birth"),
        "department": raw.get("known_for_department"),
        "popularity": raw.get("popularity") or 0,
        "homepage": raw.get("homepage"),
        "credits": entries[:60],
    }
