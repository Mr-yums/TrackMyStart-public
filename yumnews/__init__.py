"""TrackMyStart — actualité films, séries et mangas, avec espace membre et abonnement.

Point d'entrée : :func:`create_app` (fabrique Flask). Toute la composition
des objets (settings, base de données, clients d'API, passerelles de paiement)
se fait ici et uniquement ici ; le reste du code reçoit ses dépendances.
"""

from __future__ import annotations

from flask import Flask

from config import Settings
from yumnews.container import Container


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_env()
    # [Sol] Un déploiement public doit refuser les paramètres de développement.
    if settings.is_production:
        if len(settings.secret_key) < 32 or settings.secret_key in {
            "dev-secret",
            "change-me",
        }:
            raise ValueError("SECRET_KEY de production insuffisante")
        if not settings.site_url.startswith("https://"):
            raise ValueError("SITE_URL doit utiliser HTTPS en production")
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(
        SECRET_KEY=settings.secret_key,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.is_production,
        REMEMBER_COOKIE_HTTPONLY=True,
        REMEMBER_COOKIE_SECURE=settings.is_production,
        MAX_CONTENT_LENGTH=1024 * 1024,
        JSON_SORT_KEYS=False,
    )

    # [Sol] Ne jamais faire confiance aux en-têtes proxy sur une installation directe.
    if settings.trusted_proxy_hops not in (0, 1):
        raise ValueError("TRUSTED_PROXY_HOPS doit valoir 0 ou 1")
    if settings.trusted_proxy_hops:
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0
        )

    container = Container(settings)
    app.extensions["container"] = container

    from yumnews.web import register_web

    register_web(app, container)
    from yumnews.cli import register_cli

    register_cli(app, container)
    return app
