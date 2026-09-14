"""Couche web Flask : blueprints fins, gestion des erreurs, session utilisateur."""

from __future__ import annotations

from flask import Flask, g, jsonify, render_template, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFError, CSRFProtect

from yumnews.container import Container
from yumnews.services.errors import DomainError
from yumnews.web.context import AuthenticatedUser, current_policy


def register_web(app: Flask, container: Container) -> None:
    csrf = CSRFProtect(app)
    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Connectez-vous pour accéder à cette page."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str) -> AuthenticatedUser | None:
        from yumnews.repositories import UserRepository

        # [Sol] Refuser les anciens cookies et les identifiants mal formés sans erreur 500.
        import hmac

        try:
            uid, fingerprint = user_id.split(":", 1)
            uid = int(uid)
        except (ValueError, AttributeError):
            return None
        entity = UserRepository(container.db.session()).get(uid)
        if (
            entity is None
            or not entity.is_active
            or not hmac.compare_digest(entity.password_hash[-32:], fingerprint)
        ):
            return None
        return AuthenticatedUser(entity)

    @app.teardown_appcontext
    def remove_session(_exc) -> None:
        container.db.remove()

    @app.context_processor
    def inject_globals() -> dict:
        from yumnews.services.adsense import client_for_page

        policy = current_policy()
        return {
            "payments_enabled": container.settings.payments_enabled,
            "site_name": container.settings.site_name,
            "offer": container.settings.offer,
            "policy": policy,
            "adsense_client": client_for_page(
                container.settings, policy, request.endpoint
            ),
            "payment_methods": container.gateways.available(),
        }

    @app.errorhandler(DomainError)
    def handle_domain_error(exc: DomainError):
        if _wants_json():
            return jsonify(ok=False, error=exc.message, code=exc.code), exc.status_code
        return render_template(
            "public/error.html", title="Erreur", message=exc.message
        ), exc.status_code

    @app.errorhandler(CSRFError)
    def handle_csrf(exc: CSRFError):
        if _wants_json():
            return jsonify(
                ok=False, error="Session expirée, rechargez la page.", code="csrf"
            ), 400
        return render_template(
            "public/error.html",
            title="Session expirée",
            message="Rechargez la page et réessayez.",
        ), 400

    @app.errorhandler(404)
    def not_found(_exc):
        if _wants_json():
            return jsonify(ok=False, error="Introuvable.", code="not_found"), 404
        return render_template(
            "public/error.html",
            title="Page introuvable",
            message="Cette page n'existe pas.",
        ), 404

    @app.errorhandler(500)
    def server_error(_exc):
        if _wants_json():
            return jsonify(ok=False, error="Erreur interne.", code="server_error"), 500
        return render_template(
            "public/error.html",
            title="Erreur",
            message="Une erreur est survenue. Réessayez.",
        ), 500

    @app.after_request
    def security_headers(response):
        # [Sol] Le HTML public peut différer selon l'abonnement de la session.
        if response.mimetype == "text/html":
            response.headers["Cache-Control"] = "private, no-store"
            response.vary.add("Cookie")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault(
            "Referrer-Policy", "strict-origin-when-cross-origin"
        )
        return response

    from yumnews.web.advertising import advertising_bp  # [Sol]
    from yumnews.web.api.catalog import catalog_api
    from yumnews.web.api.member import member_api
    from yumnews.web.auth import auth_bp
    from yumnews.web.billing import billing_bp, webhooks_bp
    from yumnews.web.dashboard import dashboard_bp
    from yumnews.web.public import public_bp

    for bp in (
        public_bp,
        auth_bp,
        dashboard_bp,
        billing_bp,
        webhooks_bp,
        catalog_api,
        member_api,
        advertising_bp,
    ):
        app.register_blueprint(bp)
    csrf.exempt(webhooks_bp)


def _wants_json() -> bool:
    return (
        request.path.startswith(("/api/", "/webhooks/"))
        or request.is_json
        or request.accept_mimetypes.best == "application/json"
    )
