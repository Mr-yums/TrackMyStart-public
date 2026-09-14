"""[Sol] Persistance, isolation des comptes et personnalisation réelle du catalogue."""

import pytest
from unittest.mock import Mock
from yumnews.services.access_policy import FreeAccessPolicy, PremiumAccessPolicy
from yumnews.services.preference_service import DEFAULTS


def test_preferences_survive_new_session_and_drive_home(logged_client, container):
    payload = {
        "sections": ["news"],
        "news_categories": ["cinema"],
        "news_sources": ["premiere"],
        "start_tab": "me",
        "compact_cards": True,
    }
    response = logged_client.put("/api/me/preferences", json=payload)
    assert response.status_code == 200
    container.db.remove()
    assert logged_client.get("/api/me").get_json()["preferences"] == payload
    container.catalog.press.feed = Mock(
        return_value=[
            {
                "title": "Mon article",
                "url": "https://example.test/a",
                "date": "2026-09-10",
            }
        ]
    )
    container.catalog.tmdb.hero = Mock(
        side_effect=AssertionError("Section films désactivée")
    )
    container.catalog.mangadex.new_releases = Mock(
        side_effect=AssertionError("Section mangas désactivée")
    )
    home = logged_client.get("/api/home").get_json()
    assert home["movies_trending"] == [] and home["mangas_new"] == []
    assert home["headlines"][0]["title"] == "Mon article"
    container.catalog.press.feed.assert_called_once_with("premiere", limit=5)


@pytest.mark.parametrize(
    "payload",
    [
        {"sections": []},
        {"news_categories": []},
        {"news_sources": ["https://evil.test/rss"]},
        {"compact_cards": "false"},
        {"start_tab": "nope"},
        {"user_id": 9},
        {"sections": [None]},
        [],
    ],
)
def test_rejects_invalid_preferences_without_changes(logged_client, payload):
    assert logged_client.put("/api/me/preferences", json=payload).status_code == 400
    assert (
        logged_client.get("/api/me/preferences").get_json()["preferences"] == DEFAULTS
    )


def test_preferences_are_private(logged_client, app, container):
    logged_client.put("/api/me/preferences", json={"sections": ["movies"]})
    other = app.test_client()
    assert other.get("/api/me/preferences").status_code == 401
    with container.db.session_scope() as session:
        container.auth.register(
            session, "other@example.com", "a-safe-test-password", "Other"
        )
    other.post(
        "/connexion",
        data={"email": "other@example.com", "password": "a-safe-test-password"},
    )
    assert (
        other.get("/api/me/preferences").get_json()["preferences"]["sections"]
        == DEFAULTS["sections"]
    )


def test_preferences_do_not_unlock_premium_categories(container):
    prefs = {**DEFAULTS, "news_categories": ["anime"], "news_sources": ["ann"]}
    container.catalog.press.feed = Mock(return_value=[])
    assert container.catalog.personal_headlines(FreeAccessPolicy(), prefs) == []
    container.catalog.press.feed.assert_not_called()
    container.catalog.personal_headlines(PremiumAccessPolicy(), prefs)
    container.catalog.press.feed.assert_called_once_with("ann", limit=15)


def test_news_source_cannot_bypass_category_access(client, container):
    container.catalog.press.feed = Mock(side_effect=AssertionError("Accès interdit"))
    assert client.get("/api/news/cinema?source=ann").status_code == 404


def test_preference_csrf_is_enforced(app, logged_client):
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.put("/api/me/preferences", json={"start_tab": "me"}).status_code
        == 400
    )
