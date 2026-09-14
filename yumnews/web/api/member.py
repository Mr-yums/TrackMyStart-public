"""API JSON de l'espace membre : profil, acteurs suivis, liste, fil d'actualité."""

from __future__ import annotations

from flask import Blueprint, request
from flask_login import current_user

from yumnews.web.context import (
    container,
    current_policy,
    db_session,
    json_body,
    login_required_json,
    ok,
)

member_api = Blueprint("member_api", __name__, url_prefix="/api/me")


def _follow_dict(f) -> dict:
    return {
        "id": f.person_id,
        "name": f.name,
        "profile": f.profile_path,
        "department": f.department,
        "since": f.created_at.isoformat(),
    }


def _watch_dict(w) -> dict:
    return {
        "id": w.media_id,
        "media_type": w.media_type
        if isinstance(w.media_type, str)
        else w.media_type.value,
        "title": w.title,
        "poster": w.poster,
        "year": w.year,
        "since": w.created_at.isoformat(),
    }


@member_api.get("")
@login_required_json
def me():
    c = container()
    session = db_session()
    entity = current_user.entity
    return ok(
        user={
            "id": entity.id,
            "email": entity.email,
            "display_name": entity.display_name,
            "email_verified": entity.email_verified,
        },
        preferences=c.preferences.get(session, entity.id),  # [Sol]
        subscription=c.subscriptions.summary(session, entity),
        policy=current_policy().to_dict(),
        follows=[_follow_dict(f) for f in c.members.follows(session, entity)],
        watchlist=[_watch_dict(w) for w in c.members.watchlist(session, entity)],
    )


@member_api.get("/follows")
@login_required_json
def follows():
    return ok(
        results=[
            _follow_dict(f)
            for f in container().members.follows(db_session(), current_user.entity)
        ]
    )


@member_api.post("/follows")
@login_required_json
def follow():
    c = container()
    with c.db.session_scope() as session:
        entity = session.merge(current_user.entity)
        follow = c.members.follow(session, entity, current_policy(), json_body())
        data = _follow_dict(follow)
    return ok(result=data)


@member_api.delete("/follows/<int:person_id>")
@login_required_json
def unfollow(person_id: int):
    c = container()
    with c.db.session_scope() as session:
        c.members.unfollow(session, session.merge(current_user.entity), person_id)
    return ok()


@member_api.get("/feed")
@login_required_json
def feed():
    c = container()
    ids = [f.person_id for f in c.members.follows(db_session(), current_user.entity)]
    return ok(**c.catalog.person_feed(current_policy(), ids))


@member_api.get("/watchlist")
@login_required_json
def watchlist():
    return ok(
        results=[
            _watch_dict(w)
            for w in container().members.watchlist(db_session(), current_user.entity)
        ]
    )


@member_api.post("/watchlist")
@login_required_json
def add_watchlist():
    c = container()
    with c.db.session_scope() as session:
        item = c.members.add_to_watchlist(
            session, session.merge(current_user.entity), current_policy(), json_body()
        )
        data = _watch_dict(item)
    return ok(result=data)


@member_api.delete("/watchlist/<media_type>/<media_id>")
@login_required_json
def remove_watchlist(media_type: str, media_id: str):
    c = container()
    with c.db.session_scope() as session:
        c.members.remove_from_watchlist(
            session, session.merge(current_user.entity), media_type, media_id
        )
    return ok()


@member_api.route("/preferences", methods=["GET", "PUT"])
@login_required_json
def preferences():
    """[Sol] Le compte cible provient uniquement de la session authentifiée."""
    c = container()
    if request.method == "PUT":
        from yumnews.services.errors import ValidationError

        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValidationError("Objet JSON attendu.")
        with c.db.session_scope() as session:
            result = c.preferences.save(session, current_user.id, payload)
    else:
        result = c.preferences.get(db_session(), current_user.id)
    return ok(preferences=result, options=c.preferences.options(current_policy()))


# [Sol] Fil personnel et retours authentifiés ; aucune identité fournie par le client.
@member_api.get("/recommendations")
@login_required_json
def recommendations():
    from yumnews.services.errors import ValidationError

    mode = request.args.get("mode", "personal")
    if mode not in ("personal", "chronological"):
        raise ValidationError("Ordre du fil inconnu.")
    c, session = container(), db_session()
    return ok(
        **c.recommendations.feed(
            session,
            current_user.id,
            c.catalog,
            current_policy(),
            c.members.follows(session, current_user.entity),
            c.members.watchlist(session, current_user.entity),
            mode,
        )
    )


@member_api.put("/recommendations/settings")
@login_required_json
def recommendation_settings():
    c = container()
    with c.db.session_scope() as session:
        settings = c.recommendations.change(
            session, current_user.id, request.get_json(silent=True)
        )
    return ok(settings=settings)


@member_api.post("/recommendations/feedback")
@login_required_json
def recommendation_feedback():
    c = container()
    with c.db.session_scope() as session:
        c.recommendations.feedback(
            session, current_user.id, request.get_json(silent=True)
        )
    return ok()


@member_api.after_request
def private_recommendations(response):
    # [Sol] Toutes les données du compte, y compris son identité, sont privées.
    response.headers["Cache-Control"] = "private, no-store"
    response.vary.add("Cookie")
    return response


@member_api.get("/recommendations/settings")
@login_required_json
def get_recommendation_settings():
    # [Sol] Les réglages restent disponibles même si le catalogue externe est lent.
    from yumnews.services.recommendation_service import TOPICS

    return ok(
        settings=container().recommendations.settings(db_session(), current_user.id),
        topics=TOPICS,
    )


# [Sol] Statuts gratuits, filtres Premium contrôlés côté serveur.
@member_api.get("/catalog")
@login_required_json
def catalog_preferences():
    from yumnews.services.catalog_preferences import COUNTRIES

    return ok(
        catalog=container().catalog_preferences.get(db_session(), current_user.id),
        countries=COUNTRIES,
    )


@member_api.put("/catalog/filters/<kind>")
@login_required_json
def save_catalog_filters(kind):
    c = container()
    with c.db.session_scope() as session:
        values = c.catalog_preferences.save_filters(
            session,
            current_user.id,
            current_policy(),
            kind,
            request.get_json(silent=True),
        )
    return ok(filters=values)


@member_api.put("/catalog/titles/<kind>/<media_id>")
@login_required_json
def mark_catalog_title(kind, media_id):
    c = container()
    with c.db.session_scope() as session:
        values = c.catalog_preferences.mark(
            session, current_user.id, kind, media_id, request.get_json(silent=True)
        )
    return ok(status=values)
