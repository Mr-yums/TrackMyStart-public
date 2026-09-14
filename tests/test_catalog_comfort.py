"""[Sol] Distinction des plans, isolation des choix et filtres de production réels."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
import pytest
from yumnews.domain.models import User
from yumnews.domain.enums import SubscriptionStatus
from yumnews.services.catalog_preferences import DEFAULT, FILTERS
from yumnews.services.access_policy import FreeAccessPolicy, PremiumAccessPolicy
from yumnews.catalog.http import ApiUnavailable


def premium(container, user):
    with container.db.session_scope() as session:
        return container.subscriptions.activate(session, session.get(User, user)).id


def test_free_marks_persist_isolate_and_preserve_other_preferences(
    logged_client, container, user
):
    assert (
        logged_client.put(
            "/api/me/preferences", json={"compact_cards": True}
        ).status_code
        == 200
    )
    response = logged_client.put(
        "/api/me/catalog/titles/movie/12", json={"seen": True, "title": "Titre test"}
    )
    assert response.status_code == 200
    assert logged_client.get("/api/me/catalog").json["catalog"]["titles"]["movie:12"][
        "seen"
    ]
    assert logged_client.get("/api/me/preferences").json["preferences"]["compact_cards"]
    with container.db.session_scope() as session:
        other = container.auth.register(
            session, "other@example.com", "password123", "Other"
        )
        assert container.catalog_preferences.get(session, other.id)["titles"] == {}
    assert (
        logged_client.put(
            "/api/me/catalog/titles/movie/12", json={"seen": False, "disliked": False}
        ).status_code
        == 200
    )
    assert logged_client.get("/api/me/catalog").json["catalog"]["titles"] == {}


def test_filters_require_premium_and_status_validation(logged_client):
    assert (
        logged_client.put(
            "/api/me/catalog/filters/movie", json={"hide_seen": True}
        ).status_code
        == 402
    )
    for kind, identity, payload in [
        ("movie", "0", {"seen": True}),
        ("person", "1", {"seen": True}),
        ("tv", "2", {"seen": "yes"}),
        ("movie", "1", {"user_id": 3, "seen": True}),
    ]:
        assert (
            logged_client.put(
                f"/api/me/catalog/titles/{kind}/{identity}", json=payload
            ).status_code
            == 400
        )


def test_premium_filters_and_downgrade_keep_choices_without_applying(
    logged_client, container, user
):
    sid = premium(container, user)
    pool = [
        {"id": 1, "media_type": "movie", "votes": 500},
        {"id": 2, "media_type": "movie", "votes": 800},
        {"id": 3, "media_type": "movie", "votes": 10},
    ]
    original = deepcopy(pool)
    container.catalog.movies = Mock(return_value=pool)
    container.tmdb.filter_metadata = Mock(
        side_effect=lambda kind, identity: {
            "production_countries": ["FR"] if identity == 1 else ["US"],
            "runtime": 100,
        }
    )
    assert (
        logged_client.put(
            "/api/me/catalog/filters/movie",
            json={"country": "FR", "runtime_max": 120, "votes_min": 100},
        ).status_code
        == 200
    )
    result = logged_client.get("/api/movies/trending")
    assert [i["id"] for i in result.json["results"]] == [1] and result.json[
        "scanned"
    ] == 3
    assert pool == original
    assert (
        logged_client.put(
            "/api/me/catalog/titles/movie/1", json={"seen": True}
        ).status_code
        == 200
    )
    assert (
        logged_client.put(
            "/api/me/catalog/filters/movie", json={"hide_seen": True}
        ).status_code
        == 200
    )
    assert [
        i["id"] for i in logged_client.get("/api/movies/trending").json["results"]
    ] == [2, 3]
    from yumnews.domain.models import Subscription

    with container.db.session_scope() as session:
        session.get(Subscription, sid).current_period_end -= timedelta(days=40)
    assert len(logged_client.get("/api/movies/trending").json["results"]) == 3
    assert (
        logged_client.get("/api/me/catalog").json["catalog"]["filters"]["movie"][
            "hide_seen"
        ]
        is True
    )
    assert (
        logged_client.get("/api/movies/trending").headers["Cache-Control"]
        == "private, no-store"
    )


def test_unknown_metadata_is_excluded_and_outage_is_not_empty(container):
    data = deepcopy(DEFAULT)
    data["filters"]["tv"]["runtime_max"] = 45
    container.tmdb.filter_metadata = Mock(
        return_value={"runtime": None, "production_countries": ["FR"]}
    )
    items = [{"id": 1, "media_type": "tv", "votes": 1}]
    assert (
        container.catalog_preferences.filter(
            items, data, PremiumAccessPolicy(), "tv", container.tmdb
        )
        == []
    )
    container.tmdb.filter_metadata.side_effect = ApiUnavailable("test")
    with pytest.raises(ApiUnavailable):
        container.catalog_preferences.filter(
            items, data, PremiumAccessPolicy(), "tv", container.tmdb
        )


def test_filters_validate_ranges_and_csrf(app, logged_client, container, user):
    premium(container, user)
    for payload in [
        {"runtime_min": 200, "runtime_max": 90},
        {"country": "UNKNOWN"},
        {"votes_min": True},
        {"hide_seen": "false"},
    ]:
        assert (
            logged_client.put("/api/me/catalog/filters/movie", json=payload).status_code
            == 400
        )
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.put(
            "/api/me/catalog/titles/tv/1", json={"seen": True}
        ).status_code
        == 400
    )


def test_production_country_does_not_mean_original_language(container):
    container.tmdb._get = Mock(
        return_value={
            "original_language": "fr",
            "origin_country": ["CA"],
            "production_countries": [{"iso_3166_1": "US"}],
            "runtime": 96,
        }
    )
    assert container.tmdb.filter_metadata("movie", 1) == {
        "production_countries": ["US"],
        "runtime": 96,
    }
