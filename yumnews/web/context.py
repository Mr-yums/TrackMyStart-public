"""Accès aux dépendances depuis les vues + décorateurs d'accès."""

from __future__ import annotations

from functools import wraps

from flask import abort, current_app, g, jsonify, redirect, request, url_for
from flask_login import UserMixin, current_user

from yumnews.container import Container
from yumnews.domain.models import User
from yumnews.services.access_policy import AccessPolicy, AccessPolicyFactory


class AuthenticatedUser(UserMixin):
    """Adaptateur Flask-Login autour de l'entité ORM (le domaine ignore Flask)."""

    def __init__(self, entity: User) -> None:
        self.entity = entity

    def get_id(self) -> str:
        # [Sol] Un changement de mot de passe révoque les sessions et cookies mémorisés.
        return f"{self.entity.id}:{self.entity.password_hash[-32:]}"

    @property
    def id(self) -> int:
        return self.entity.id

    @property
    def email(self) -> str:
        return self.entity.email

    @property
    def display_name(self) -> str:
        return self.entity.display_name

    @property
    def is_admin(self) -> bool:
        return self.entity.is_admin


def container() -> Container:
    return current_app.extensions["container"]


def db_session():
    return container().db.session()


def current_entity() -> User | None:
    return current_user.entity if current_user.is_authenticated else None


def current_policy() -> AccessPolicy:
    if "policy" not in g:
        entity = current_entity()
        if entity is None:
            g.policy = AccessPolicyFactory.for_plan(None)
        else:
            g.policy = container().subscriptions.policy_for(db_session(), entity)
    return g.policy


def json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def ok(**payload):
    return jsonify(ok=True, **payload)


def login_required_json(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify(
                ok=False,
                error="Connexion requise.",
                code="login_required",
                login_url=url_for("auth.login"),
            ), 401
        return view(*args, **kwargs)

    return wrapper


def client_ip() -> str:
    # [Sol] Seul ProxyFix, explicitement configuré derrière le proxy, interprète les en-têtes.
    # [Sol] Identifiant de compteur en dernier recours, aucune écoute réseau.
    return request.remote_addr or "0.0.0.0"  # nosec B104
