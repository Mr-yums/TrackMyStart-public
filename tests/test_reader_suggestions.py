"""[Sol] Presse dynamique : préférences, droits, pagination et panne partielle."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import time
import pytest

from yumnews.services.reader_suggestions import ReaderSuggestions, canonical
from yumnews.services.recommendation_service import DEFAULT
from yumnews.catalog.http import ApiUnavailable
from yumnews.services.access_policy import FreeAccessPolicy
from yumnews.services.preference_service import DEFAULTS
from yumnews.catalog.news.sources import SOURCES_BY_KEY
from yumnews.editorial.stories import STORIES


def article(n, title=None, source="premiere"):
    return {
        "title": title or f"Un nouveau projet numéro {n}",
        "link": f"https://example.com/a/{n}",
        "reader_url": f"/lecture/signed-{n}",
        "image": "https://example.com/photo.jpg",
        "source": {"key": source, "name": source},
        "category": "cinema",
        "description": "Un projet au cinéma.",
        "date": None,
    }


def test_follow_names_watchlist_topics_and_current_are_used():
    pool = [
        article(1, "Maria Sten rejoint un casting"),
        article(2, "Un projet Reacher est annoncé"),
        article(3, "Netflix prépare une série"),
        article(4),
    ]
    settings = deepcopy(DEFAULT)
    settings["muted"] = ["netflix"]
    context = {
        "title": "Article actuellement lu",
        "url": pool[3]["link"] + "?utm_source=test",
    }
    result = ReaderSuggestions.rank(
        pool,
        settings,
        [SimpleNamespace(name="Maria Sten")],
        [SimpleNamespace(title="Reacher")],
        context,
        time.time(),
    )
    assert len(result) == 2
    assert result[0]["reason"] == "Vous suivez Maria Sten"
    assert result[1]["reason"] == "Dans votre liste : Reacher"
    assert result[0]["image"].endswith("photo.jpg")
    settings["feedback"][result[0]["id"]] = {"action": "hide", "topics": []}
    assert (
        len(ReaderSuggestions.rank(pool, settings, [], [], context, time.time())) == 1
    )


def test_same_titles_and_tracking_urls_are_deduplicated_and_no_fake_match():
    a = article(1, "Emma Stone : un film")
    b = {**a, "link": a["link"] + "?utm_campaign=promo"}
    c = {**a, "link": "https://another.example/a"}
    result = ReaderSuggestions.rank(
        [a, b, c],
        deepcopy(DEFAULT),
        [SimpleNamespace(name="Stone")],
        [],
        {"title": "Other", "url": "https://other.example"},
        time.time(),
    )
    assert len(result) == 1
    assert canonical(a["link"]) == canonical(b["link"])


def test_paging_is_stable_and_bound_to_user_and_source_policy(container):
    service = container.reader_suggestions
    container.catalog.press.feed = Mock(
        side_effect=lambda key, limit: [
            article(f"{key}-{n}", source=key) for n in range(limit)
        ]
    )
    args = (
        container.catalog,
        FreeAccessPolicy(),
        deepcopy(DEFAULTS),
        deepcopy(DEFAULT),
        [],
        [],
        {"title": "Current", "url": "https://current.test"},
        42,
    )
    first = service.page(*args)
    second = service.page(*args, cursor=first["next_cursor"])
    assert len(first["items"]) == len(second["items"]) == 12
    assert not set(i["id"] for i in first["items"]) & set(
        i["id"] for i in second["items"]
    )
    assert all(
        SOURCES_BY_KEY[call.args[0]].category in ("cinema", "series")
        for call in container.catalog.press.feed.call_args_list
    )
    with pytest.raises(Exception, match="invalide"):
        service.page(*args[:-1], 43, cursor=first["next_cursor"])
    container.catalog.press.feed = Mock(return_value=[])
    assert service.page(*args, cursor=first["next_cursor"])["changed"] is True


def test_partial_outage_and_explicit_source_selection(container):
    def fetch(key, limit):
        if key == "premiere":
            raise ApiUnavailable("test")
        return [article(1)]

    container.catalog.press.feed = Mock(side_effect=fetch)
    prefs = {**DEFAULTS, "news_sources": ["premiere", "variety-film"]}
    result = container.reader_suggestions.page(
        container.catalog,
        FreeAccessPolicy(),
        prefs,
        deepcopy(DEFAULT),
        [],
        [],
        {"title": "Current", "url": "https://current.test"},
        1,
    )
    assert len(result["items"]) == 1
    assert set(
        call.args[0] for call in container.catalog.press.feed.call_args_list
    ) == {"premiere", "variety-film"}


def test_reader_api_returns_real_signed_reading_links_and_feedback(
    logged_client, container
):
    item = container.news._article(
        {
            "title": "Une nouvelle série Netflix",
            "link": "https://www.premiere.fr/test",
            "summary": "Un extrait de test",
            "media_thumbnail": [{"url": "https://example.com/photo.jpg"}],
        },
        SOURCES_BY_KEY["premiere"],
    )
    container.catalog.press.feed = Mock(return_value=[item])
    result = logged_client.post(
        "/api/reader/suggestions", json={"context": {"slug": STORIES[0]["slug"]}}
    )
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "private, no-store"
    card = result.json["items"][0]
    assert (
        card["url"].startswith("/lecture/")
        and card["image"] == "https://example.com/photo.jpg"
    )
    assert logged_client.get(card["url"]).status_code == 200
    assert (
        logged_client.post(
            "/api/me/recommendations/feedback",
            json={"token": card["feedback_token"], "action": "hide"},
        ).status_code
        == 200
    )
    assert (
        logged_client.post(
            "/api/reader/suggestions", json={"context": {"slug": STORIES[0]["slug"]}}
        ).json["items"]
        == []
    )


def test_unknown_context_no_fetch_and_csrf(app, logged_client, container):
    container.catalog.press.feed = Mock(side_effect=AssertionError("Pas de chargement"))
    assert (
        logged_client.post(
            "/api/reader/suggestions",
            json={"context": {"url": "http://localhost/private"}},
        ).status_code
        == 400
    )
    assert (
        logged_client.post(
            "/api/reader/suggestions", json={"context": {"token": "fake"}}
        ).status_code
        == 404
    )
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.post(
            "/api/reader/suggestions", json={"context": {"slug": STORIES[0]["slug"]}}
        ).status_code
        == 400
    )


def test_date_order_without_personalization_and_freshness_cutoff():
    now = time.time()
    pool = []
    for n, age in enumerate([1, 2, 3, 4, 91, -2]):
        item = article(n, source="premiere" if n < 3 else "variety-film")
        item["date"] = datetime.fromtimestamp(
            now - age * 86400, timezone.utc
        ).isoformat()
        pool.append(item)
    settings = {**deepcopy(DEFAULT), "enabled": False}
    result = ReaderSuggestions.rank(
        pool, settings, [], [], {"title": "Other", "url": "https://other.example"}, now
    )
    assert [item["url"] for item in result] == [
        f"/lecture/signed-{n}" for n in range(4)
    ]
