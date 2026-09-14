"""[Sol] Vérifications bloquantes de l'image et du serveur candidat."""

import argparse
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check(get):
    for path in (
        "/",
        "/connexion",
        "/inscription",
        "/tarifs",
        "/mentions-legales",
        "/actualites",
        "/actualites/netflix-lust-stories-3-septembre",
        "/actualites/prime-video-neagley-maria-sten",
    ):
        status, text, headers = get(path)
        assert status == 200, (path, status)
        assert "TrackMyStart" in text and "YumNews" not in text, path
        assert headers.get("X-Content-Type-Options") == "nosniff", path
    for path in (
        "/static/css/trackmystart.css",
        "/static/js/app.js",
        "/static/img/favicon.svg",
        "/static/css/editorial-polish.css",
        "/static/js/editorial-polish.js",
        "/static/js/landing-background.js",
        "/static/js/catalog-comfort.js",
        "/static/js/advertising.js",
        "/static/js/advertising-admin.js",
        "/static/js/reading-room.js",
    ):
        assert get(path)[0] == 200, path
    assert get("/api/me")[0] == 401, "API privée accessible sans connexion"
    assert get("/api/admin/advertising")[0] == 401, (
        "Administration publicitaire non protégée"
    )
    assert get("/app")[0] == 302, "Dashboard privé non protégé"
    status, text, _ = get("/pret")
    assert status == 200, ("Base indisponible", status)
    import json

    health = json.loads(text)
    assert health["service"] == "trackmystart" and health["status"] == "ok"
    expected = os.environ.get("RELEASE_ID")
    if expected:
        assert health["release"] == expected, "Mauvaise version servie"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolated", action="store_true")
    parser.add_argument("--url", default="http://127.0.0.1:8800")
    args = parser.parse_args()
    if args.isolated:
        from config import Settings
        from yumnews import create_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                Settings(env="testing", db_url=f"sqlite:///{directory}/check.db")
            )
            app.extensions["container"].db.create_all()
            client = app.test_client()

            def get(path):
                r = client.get(path)
                return r.status_code, r.get_data(as_text=True), r.headers

            check(get)
    else:
        import requests

        def get(path):
            r = requests.get(
                args.url.rstrip("/") + path, timeout=15, allow_redirects=False
            )
            return r.status_code, r.text, r.headers

        check(get)
    print("PASS : pages, marque, ressources, accès privés, base et version")


if __name__ == "__main__":
    main()
