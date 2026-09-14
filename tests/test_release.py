"""[Sol] Conditions de publication : santé de la base et configuration publique."""

from dataclasses import replace

import pytest
from sqlalchemy.exc import OperationalError

from yumnews import create_app


def test_readiness_identifies_release(client, monkeypatch):
    monkeypatch.setenv("RELEASE_ID", "abc123")
    response = client.get("/pret")
    assert response.status_code == 200
    assert response.json == {
        "status": "ok",
        "service": "trackmystart",
        "release": "abc123",
    }


def test_readiness_fails_when_database_is_down(client, container, monkeypatch):
    def unavailable():
        raise OperationalError("connection", {}, Exception("private database details"))

    monkeypatch.setattr(container.db.engine, "connect", unavailable)
    response = client.get("/pret")
    assert response.status_code == 503
    assert "private" not in response.get_data(as_text=True)


def test_production_rejects_weak_secret(settings):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app(
            replace(settings, env="production", site_url="https://trackmystart.de")
        )


def test_production_rejects_http(settings):
    with pytest.raises(ValueError, match="HTTPS"):
        create_app(replace(settings, env="production", secret_key="x" * 64))


def test_production_cookies_are_secure(settings):
    app = create_app(
        replace(
            settings,
            env="production",
            secret_key="x" * 64,
            site_url="https://trackmystart.de",
        )
    )
    assert app.config["SESSION_COOKIE_SECURE"]
    assert app.config["REMEMBER_COOKIE_SECURE"]
