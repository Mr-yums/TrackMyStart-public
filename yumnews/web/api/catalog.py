"""API JSON du catalogue, consommée par le dashboard."""

from __future__ import annotations

from flask import Blueprint, Response, request

from yumnews.catalog.http import ApiUnavailable
from yumnews.web.context import (
    container,
    current_policy,
    current_entity,
    db_session,
    ok,
)

catalog_api = Blueprint("catalog_api", __name__, url_prefix="/api")


@catalog_api.errorhandler(ApiUnavailable)
def upstream_error(exc):
    return {
        "ok": False,
        "error": "Source externe indisponible, réessayez dans un instant.",
        "code": "upstream",
    }, 503


@catalog_api.get("/meta")
def meta():
    c = container()
    return ok(
        genres=c.tmdb.genres(),
        platforms=c.tmdb.platforms(),
        manga_genres=c.mangadex.genres(),
        news_categories=c.catalog.news_categories(current_policy()),
        policy=current_policy().to_dict(),
        tmdb=c.tmdb.configured,
    )


@catalog_api.get("/landing/visuals")
def landing_visuals():
    # [Sol] Chargement indépendant : une panne de catalogue ne bloque pas l’accueil.
    return ok(results=container().catalog.landing_visuals())


@catalog_api.get("/home")
def home():
    # [Sol] Appliquer les préférences côté serveur, sans modifier les caches partagés.
    c = container()
    entity = current_entity()
    prefs = c.preferences.get(db_session(), entity.id if entity else None)
    data = c.catalog.home(current_policy(), prefs)
    for key in ("hero", "movies_trending", "series_trending", "now_playing"):
        data[key] = _visible(data[key])
    return ok(**data)


@catalog_api.get("/movies/<list_key>")
def movies(list_key: str):
    sort = request.args.get("sort", "popularity")
    return _filtered(
        container().catalog.movies(current_policy(), list_key, sort), "movie"
    )


@catalog_api.get("/series/<path:list_key>")
def series(list_key: str):
    sort = request.args.get("sort", "popularity")
    return _filtered(container().catalog.series(current_policy(), list_key, sort), "tv")


@catalog_api.get("/upcoming")
def upcoming():
    data = container().catalog.upcoming(current_policy())
    return ok(**{key: _visible(items) for key, items in data.items()})


@catalog_api.get("/detail/<media_type>/<int:media_id>")
def detail(media_type: str, media_id: int):
    return ok(result=container().catalog.detail(current_policy(), media_type, media_id))


@catalog_api.get("/tv/<int:tv_id>/seasons")
def seasons(tv_id: int):
    return ok(seasons=container().catalog.seasons(current_policy(), tv_id))


@catalog_api.get("/search")
def search():
    data = container().catalog.search(request.args.get("q", ""))
    data["results"] = _visible(data["results"])
    return ok(**data)


@catalog_api.get("/people")
def people():
    page = request.args.get("page", 1, type=int)
    return ok(**container().catalog.people(page))


@catalog_api.get("/person/<int:person_id>")
def person(person_id: int):
    return ok(result=container().catalog.person(person_id))


@catalog_api.get("/mangas/genres")
def manga_genres():
    return ok(genres=container().mangadex.genres())


@catalog_api.get("/mangas/cover")
def manga_cover():
    url = request.args.get("url", "")
    try:
        content, content_type = container().mangadex.cover_bytes(url)
    except ValueError:
        return {"ok": False, "error": "URL refusée."}, 400
    return Response(
        content,
        content_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@catalog_api.get("/mangas/detail/<manga_id>")
def manga_detail(manga_id: str):
    return ok(result=container().catalog.manga(manga_id))


@catalog_api.get("/mangas/<list_key>")
def mangas(list_key: str):
    data = container().catalog.mangas(
        current_policy(),
        list_key,
        sort=request.args.get("sort", "popular"),
        offset=request.args.get("offset", 0, type=int),
        year=request.args.get("year"),
    )
    return ok(**data)


@catalog_api.get("/anime/schedule")
def anime_schedule():
    return ok(results=container().catalog.anime_schedule(current_policy()))


@catalog_api.get("/news/categories")
def news_categories():
    c = container()
    return ok(
        categories=c.catalog.news_categories(current_policy()), sources=c.news.sources()
    )


@catalog_api.get("/news/<category>")
def news(category: str):
    return ok(
        articles=container().catalog.news(
            current_policy(), category, request.args.get("source")
        )
    )


# [Sol] Préférences lues après le cache catalogue ; jamais injectées dans ce cache.
def _catalog_state():
    entity = current_entity()
    return container().catalog_preferences.get(
        db_session(), entity.id if entity else None
    )


def _visible(items):
    return container().catalog_preferences.visible(
        items, _catalog_state(), current_policy()
    )


def _filtered(items, kind):
    c = container()
    return ok(
        results=c.catalog_preferences.filter(
            items, _catalog_state(), current_policy(), kind, c.tmdb
        ),
        scanned=len(items),
    )


@catalog_api.after_request
def private_catalog(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response
