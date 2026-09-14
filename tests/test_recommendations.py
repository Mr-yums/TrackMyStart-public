"""[Sol] Calibration, exclusions, démarrage à froid et isolation des retours."""

from copy import deepcopy
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from yumnews.services.recommendation_service import DEFAULT, rank
from yumnews.services.access_policy import FreeAccessPolicy

TODAY = date(2026, 9, 10)


def item(key, people=None, topics=None, day="2026-09-10", confidence=3):
    return {
        "id": key,
        "title": key,
        "people": people or [],
        "topics": topics or ["cinema"],
        "date": day,
        "confidence": confidence,
    }


def test_follows_outrank_popularity_and_feedback_is_bounded():
    state = deepcopy(DEFAULT)
    state["feedback"] = {
        str(n): {"action": "more", "topics": ["cinema"]} for n in range(100)
    }
    pool = [item("star", ["Star"], ["series"])] + [item(str(n)) for n in range(100)]
    result = rank(pool, state, set(), TODAY)
    assert [i["id"] for i in result] == [
        "star"
    ]  # Pas de remplissage qui noie le suivi.


def test_diversity_and_discovery_cap_and_no_duplicates():
    pool = [item(f"{s}-{n}", [s]) for s in ["A", "B", "C", "D"] for n in range(10)]
    pool += [item(f"discover-{n}") for n in range(20)] + [pool[0]]
    result = rank(pool, deepcopy(DEFAULT), set(), TODAY)
    assert len(result) == len({i["id"] for i in result}) == 12
    assert sum(not i["people"] for i in result) == 2
    assert all(
        sum(i["people"] == [s] for i in result) <= 3 for s in ["A", "B", "C", "D"]
    )


def test_hide_and_muted_beat_follow_and_watchlist_even_chronological():
    state = deepcopy(DEFAULT)
    state["muted"] = ["casting"]
    state["feedback"] = {"hidden": {"action": "hide", "topics": ["cinema"]}}
    pool = [item("hidden", ["A"]), item("muted", ["B"], ["casting"]), item("ok", ["C"])]
    for chronological in (False, True):
        assert [
            i["id"]
            for i in rank(pool, state, {"hidden", "muted"}, TODAY, chronological)
        ] == ["ok"]


def test_official_ahead_of_negotiations_and_less_really_demotes():
    pool = [
        item("reported", ["A"], confidence=2),
        item("official", ["A"], confidence=3),
    ]
    state = deepcopy(DEFAULT)
    assert rank(pool, state, set(), TODAY)[0]["id"] == "official"
    state["feedback"]["official"] = {"action": "less", "topics": ["cinema"]}
    assert rank(pool, state, set(), TODAY)[0]["id"] == "reported"


def test_cold_start_is_editorial_and_chronological_ignores_affinity():
    result = rank(
        [item("new"), item("old", day="2026-09-01")], deepcopy(DEFAULT), set(), TODAY
    )
    assert all(i["reason"] == "Découverte éditoriale sourcée" for i in result)
    assert (
        rank(
            [item("old", ["Star"], day="2026-09-01"), item("new")],
            deepcopy(DEFAULT),
            set(),
            TODAY,
            True,
        )[0]["id"]
        == "new"
    )


def test_candidates_real_links_no_guessed_tv_appearance(container):
    container.catalog.person_feed = Mock(
        return_value={"upcoming": [], "recent": [], "locked": True}
    )
    follows = [
        SimpleNamespace(person_id=1, name="Maria Sten"),
        SimpleNamespace(person_id=2, name="Anne-Élisabeth Lemoine"),
    ]
    result, locked = container.recommendations.candidates(
        container.catalog, FreeAccessPolicy(), follows, TODAY
    )
    assert locked
    assert next(i for i in result if "neagley" in i["id"])["people"] == ["Maria Sten"]
    assert next(i for i in result if "c-a-vous" in i["id"])["people"] == []
    assert (
        container.recommendations.candidates(
            container.catalog, FreeAccessPolicy(), follows, date(2027, 1, 1)
        )[0]
        == []
    )


@pytest.fixture()
def feed_stub(container):
    container.recommendations.candidates = Mock(
        return_value=([item("story:one", ["A"])], False)
    )


def test_feedback_persists_idempotent_and_preferences_survive(
    logged_client, container, feed_stub
):
    response = logged_client.get("/api/me/recommendations")
    assert response.headers["Cache-Control"] == "private, no-store"
    token = response.json["items"][0]["token"]
    for _ in range(3):
        assert (
            logged_client.post(
                "/api/me/recommendations/feedback",
                json={"token": token, "action": "more"},
            ).status_code
            == 200
        )
    logged_client.put("/api/me/preferences", json={"compact_cards": True})
    container.db.remove()
    current = logged_client.get("/api/me/recommendations").json
    assert len(current["settings"]["feedback"]) == 1
    assert (
        logged_client.get("/api/me/preferences").json["preferences"]["compact_cards"]
        is True
    )
    assert (
        logged_client.post(
            "/api/me/recommendations/feedback", json={"token": token, "action": "hide"}
        ).status_code
        == 200
    )
    assert logged_client.get("/api/me/recommendations").json["items"] == []
    assert (
        logged_client.put(
            "/api/me/recommendations/settings", json={"remove": "story:one"}
        ).status_code
        == 200
    )
    assert len(logged_client.get("/api/me/recommendations").json["items"]) == 1
    logged_client.put(
        "/api/me/recommendations/settings", json={"enabled": False, "muted": ["cinema"]}
    )
    assert (
        logged_client.put(
            "/api/me/recommendations/settings", json={"reset": True}
        ).json["settings"]
        == DEFAULT
    )
    assert (
        logged_client.get("/api/me/preferences").json["preferences"]["compact_cards"]
        is True
    )


def test_personal_tokens_cannot_be_replayed_on_another_account(
    app, logged_client, container, feed_stub
):
    token = logged_client.get("/api/me/recommendations").json["items"][0]["token"]
    other = app.test_client()
    assert other.get("/api/me/recommendations").status_code == 401
    assert (
        other.post(
            "/api/me/recommendations/feedback", json={"token": token, "action": "hide"}
        ).status_code
        == 401
    )
    with container.db.session_scope() as session:
        container.auth.register(
            session, "second@example.com", "another-safe-password", "Second"
        )
    other.post(
        "/connexion",
        data={"email": "second@example.com", "password": "another-safe-password"},
    )
    assert (
        other.post(
            "/api/me/recommendations/feedback", json={"token": token, "action": "hide"}
        ).status_code
        == 400
    )
    assert other.get("/api/me/recommendations").json["settings"] == DEFAULT
    assert (
        logged_client.post(
            "/api/me/recommendations/feedback",
            json={"token": token + "x", "action": "hide"},
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"user_id": 1},
        {"enabled": "false"},
        {"muted": ["unknown"]},
        {"muted": [{}]},
        {"reset": False},
    ],
)
def test_bad_settings_rejected(logged_client, payload):
    assert (
        logged_client.put("/api/me/recommendations/settings", json=payload).status_code
        == 400
    )


def test_feedback_csrf_required(app, logged_client, feed_stub):
    token = logged_client.get("/api/me/recommendations").json["items"][0]["token"]
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.post(
            "/api/me/recommendations/feedback", json={"token": token, "action": "hide"}
        ).status_code
        == 400
    )


def test_saved_title_boost_and_topic_feedback_change_discovery_order():
    pool = [item("cinema"), item("series", topics=["series"])]
    state = deepcopy(DEFAULT)
    state["feedback"]["previous"] = {"action": "more", "topics": ["series"]}
    assert rank(pool, state, set(), TODAY)[0]["id"] == "series"
    assert rank(pool, state, {"cinema"}, TODAY)[0]["id"] == "cinema"


def test_settings_available_without_loading_external_catalog(logged_client, container):
    container.recommendations.candidates = Mock(
        side_effect=AssertionError("Catalogue non nécessaire")
    )
    response = logged_client.get("/api/me/recommendations/settings")
    assert response.status_code == 200
    assert response.json["settings"] == DEFAULT
    assert "project" in response.json["topics"]
    assert response.headers["Cache-Control"] == "private, no-store"
