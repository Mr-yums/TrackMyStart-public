"""[Sol] Aucun SDK publicitaire pour Premium, paiement, erreurs ou mode désactivé."""

from dataclasses import replace

from yumnews import create_app
from yumnews.domain.models import User

SDK = "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js"


def test_adsense_off_by_default(client):
    assert SDK not in client.get("/").text


def test_adsense_free_premium_and_sensitive_routes(settings):
    app = create_app(replace(settings, adsense_enabled=True, adsense_client="ca-pub-0000000000000000"))
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    container = app.extensions["container"]
    container.db.create_all()
    try:
        with container.db.session_scope() as session:
            user = container.auth.register(
                session, "reader@example.com", "test-password-long", "Reader"
            )
            session.flush()
            uid = user.id
        client = app.test_client()
        response = client.get("/")
        assert SDK in response.text
        assert "private, no-store" == response.headers["Cache-Control"]
        for path in ("/connexion", "/mentions-legales", "/tarifs", "/absent"):
            assert SDK not in client.get(path).text
        client.post(
            "/connexion",
            data={"email": "reader@example.com", "password": "test-password-long"},
        )
        assert SDK in client.get("/app").text
        assert SDK not in client.get("/compte").text
        assert SDK not in client.get("/abonnement").text
        with container.db.session_scope() as session:
            container.subscriptions.activate(session, session.get(User, uid))
        for path in ("/", "/app", "/actualites"):
            page = client.get(path).text
            assert SDK not in page
            assert "google-consent.js" not in page
    finally:
        container.db.remove()
