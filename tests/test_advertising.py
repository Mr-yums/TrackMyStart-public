"""[Sol] Diffusion facultative, dates, administrateur et absence absolue en Premium."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
import pytest
from yumnews.services.advertising import Advertising, DEFAULT
from yumnews.services.access_policy import FreeAccessPolicy, PremiumAccessPolicy
from yumnews.services.errors import ValidationError
from yumnews.domain.models import User


def campaign():
    now = datetime.now(timezone.utc)
    return {
        "enabled": True,
        "interstitial": False,
        "campaign": {
            "title": "Un film test",
            "description": "Une campagne de test",
            "sponsor": "Studio test",
            "image_url": "https://example.com/image.jpg",
            "target_url": "https://example.com/film",
            "starts_at": (now - timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "placements": ["home", "catalog", "reader", "actor_break"],
        },
    }


def test_campaign_empty_dates_and_premium_before_file_read(tmp_path):
    ads = Advertising(tmp_path / "ads.json")
    assert ads.placement(FreeAccessPolicy(), "home") is None
    ads.save(campaign(), ads.read()[1])
    assert ads.placement(FreeAccessPolicy(), "home")["title"] == "Un film test"
    assert ads.placement(FreeAccessPolicy(), "actor_break") is None
    assert (
        ads.placement(
            FreeAccessPolicy(), "home", datetime.now(timezone.utc) + timedelta(days=2)
        )
        is None
    )
    ads.read = Mock(side_effect=AssertionError("Aucune campagne lue pour Premium"))
    assert ads.placement(PremiumAccessPolicy(), "home") is None


def test_revision_atomicity_and_validation(tmp_path):
    ads = Advertising(tmp_path / "ads.json")
    revision = ads.read()[1]
    ads.save(campaign(), revision)
    with pytest.raises(ValidationError):
        ads.save(DEFAULT, revision)
    invalid = campaign()
    invalid["campaign"]["image_url"] = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        ads.save(invalid, ads.read()[1])
    assert ads.read()[0]["enabled"] is True
    ads.path.write_text("broken")
    assert ads.placement(FreeAccessPolicy(), "home") is None


def test_admin_access_csrf_and_free_premium_delivery(
    app, logged_client, container, user, tmp_path
):
    container.advertising = Advertising(tmp_path / "ads.json")
    assert logged_client.get("/admin/publicite").status_code == 403
    assert logged_client.put("/api/admin/advertising", json={}).status_code == 403
    with container.db.session_scope() as session:
        session.get(User, user).is_admin = True
    config = logged_client.get("/api/admin/advertising").json
    assert (
        logged_client.put(
            "/api/admin/advertising",
            json={"revision": config["revision"], "config": campaign()},
        ).status_code
        == 200
    )
    assert (
        logged_client.get("/api/ads/home").json["campaign"]["sponsor"] == "Studio test"
    )
    assert (
        logged_client.get("/api/ads/home").headers["Cache-Control"]
        == "private, no-store"
    )
    assert logged_client.get("/admin/publicite").status_code == 200
    with container.db.session_scope() as session:
        container.subscriptions.activate(session, session.get(User, user))
    assert logged_client.get("/api/ads/home").json["campaign"] is None
    assert "data-ad-placement=" not in logged_client.get("/app").text
    app.config["WTF_CSRF_ENABLED"] = True
    assert (
        logged_client.put(
            "/api/admin/advertising", json={"config": DEFAULT}
        ).status_code
        == 400
    )
