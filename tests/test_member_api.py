def test_follow_quota_for_free_plan(logged_client):
    for i in range(3):
        r = logged_client.post(
            "/api/me/follows",
            json={"id": 100 + i, "name": f"Actor {i}", "profile": None},
        )
        assert r.status_code == 200
    r = logged_client.post(
        "/api/me/follows", json={"id": 999, "name": "Trop", "profile": None}
    )
    assert r.status_code == 402 and r.get_json()["code"] == "quota_exceeded"
    # Re-suivre un acteur déjà suivi est idempotent
    assert (
        logged_client.post(
            "/api/me/follows", json={"id": 100, "name": "Actor 0"}
        ).status_code
        == 200
    )
    assert logged_client.delete("/api/me/follows/100").status_code == 200
    assert len(logged_client.get("/api/me/follows").get_json()["results"]) == 2


def test_watchlist_validation(logged_client):
    assert (
        logged_client.post(
            "/api/me/watchlist", json={"media_type": "book", "id": "1"}
        ).status_code
        == 400
    )
    r = logged_client.post(
        "/api/me/watchlist",
        json={"media_type": "movie", "id": 550, "title": "Fight Club", "year": "1999"},
    )
    assert r.status_code == 200 and r.get_json()["result"]["title"] == "Fight Club"
    assert logged_client.delete("/api/me/watchlist/movie/550").status_code == 200
    assert logged_client.delete("/api/me/watchlist/movie/550").status_code == 404


def test_anonymous_is_rejected_on_member_api(client):
    assert client.get("/api/me").status_code == 401
    assert (
        client.post("/api/me/follows", json={"id": 1, "name": "x"}).status_code == 401
    )
