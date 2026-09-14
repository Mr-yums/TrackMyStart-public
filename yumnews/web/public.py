from __future__ import annotations

from flask import Blueprint, abort, render_template, request

from yumnews.editorial.stories import STORIES, story_by_slug

public_bp = Blueprint("public", __name__)


@public_bp.get("/")
def home():
    # [Sol] Accueil accessible aussi aux membres via le lien de navigation.
    return render_template("public/landing.html", stories=STORIES)


# [Sol] Lecture éditoriale sur le site ; consultation des originaux facultative.
@public_bp.get("/actualites")
def news_index():
    return render_template("public/news_index.html", stories=STORIES)


@public_bp.get("/actualites/<slug>")
def news_article(slug):
    story = story_by_slug(slug)
    if story is None:
        abort(404)
    return render_template(
        "public/news_article.html", story=story, reader_context={"slug": slug}
    )


@public_bp.get("/tarifs")
def pricing():
    from yumnews.web.context import container

    if not container().settings.payments_enabled:
        return preregistration()
    return render_template("public/pricing.html")


@public_bp.get("/mentions-legales")
def legal():
    return render_template("public/legal.html")


@public_bp.get("/sante")
def health():
    return {"status": "ok", "service": "trackmystart"}


@public_bp.get("/pret")
def readiness():
    """[Sol] Contrôle de disponibilité réel utilisé avant et après la bascule."""
    import os
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError
    from yumnews.domain.models import User
    from yumnews.web.context import container

    try:
        with container().db.engine.connect() as connection:
            connection.execute(select(User.id).limit(1))
    except SQLAlchemyError:
        return {"status": "unavailable", "service": "trackmystart"}, 503
    return {
        "status": "ok",
        "service": "trackmystart",
        "release": os.environ.get("RELEASE_ID", "local"),
    }


@public_bp.get("/lecture/<token>")
def press_article(token):
    """[Sol] Aucun URL arbitraire chargé : uniquement un extrait signé par le serveur."""
    from yumnews.web.context import container, current_policy
    from yumnews.catalog.news.sources import SOURCES_BY_KEY, CATEGORIES

    article = container().press_reader.read(token)
    if article is None:
        abort(404)
    source = SOURCES_BY_KEY[article["source"]]
    if not current_policy().news_category_allowed(source.category):
        current_policy().require("news_full")
    theme = "cinema"
    title = article["title"].casefold()
    if "netflix" in title:
        theme = "netflix"
    elif "prime video" in title or "amazon prime" in title:
        theme = "prime"
    elif source.category == "series":
        theme = "television"
    return render_template(
        "public/press_article.html",
        article=article,
        source=source,
        category=CATEGORIES[source.category],
        theme=theme,
        reader_context={"token": token},
    )


@public_bp.post("/api/reader/suggestions")
def reader_suggestions():
    # [Sol] Sources et droits choisis côté serveur ; aucun URL utilisateur n'est chargé.
    from flask_login import current_user
    from yumnews.web.context import container, current_policy, db_session, ok
    from yumnews.services.preference_service import DEFAULTS
    from yumnews.services.recommendation_service import DEFAULT
    from yumnews.catalog.news.sources import SOURCES_BY_KEY

    c = container()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"context", "cursor"}:
        abort(400)
    context = payload.get("context")
    if not isinstance(context, dict):
        abort(400)
    if set(context) == {"slug"} and isinstance(context["slug"], str):
        story = story_by_slug(context["slug"])
        if story is None:
            abort(404)
        current = {"url": story["source_url"], "title": story["title"]}
    elif set(context) == {"token"} and isinstance(context["token"], str):
        current = c.press_reader.read(context["token"])
        if current is None:
            abort(404)
        if not current_policy().news_category_allowed(
            SOURCES_BY_KEY[current["source"]].category
        ):
            current_policy().require("news_full")
    else:
        abort(400)
    uid = current_user.id if current_user.is_authenticated else 0
    session = db_session()
    prefs = c.preferences.get(session, uid) if uid else DEFAULTS
    settings = c.recommendations.settings(session, uid) if uid else DEFAULT
    follows = c.members.follows(session, current_user.entity) if uid else []
    watchlist = c.members.watchlist(session, current_user.entity) if uid else []
    result = c.reader_suggestions.page(
        c.catalog,
        current_policy(),
        prefs,
        settings,
        follows,
        watchlist,
        current,
        uid,
        payload.get("cursor"),
    )
    for item in result["items"]:
        if uid:
            item["feedback_token"] = c.recommendations.signer.dumps(
                {
                    "user": uid,
                    "id": item["id"],
                    "title": item["title"],
                    "topics": item["topics"],
                }
            )
        item.pop("score", None)
        item.pop("topics", None)
    response = ok(**result)
    response.headers["Cache-Control"] = "private, no-store"
    return response


@public_bp.get("/ads.txt")
def ads_txt():
    """[Sol] Déclaration publique AdSense, sans activer de publicité."""
    from flask import current_app, send_from_directory
    from pathlib import Path

    return send_from_directory(
        Path(current_app.root_path).parent / "ops" / "publisher",
        "ads.txt",
        mimetype="text/plain",
    )


# [Sol] Information publique sur les données et le consentement.
@public_bp.get("/confidentialite")
def privacy():
    return render_template("public/privacy.html")


# [Sol] Canaux d’assistance.
@public_bp.get("/aide")
def support():
    return render_template("public/support.html")


# [Sol] Une inscription sur liste d’attente n’ouvre aucun droit Premium.
@public_bp.route("/preinscription", methods=["GET", "POST"])
def preregistration():
    from flask import request, redirect, url_for, flash
    from flask_login import current_user
    from yumnews.web.context import container
    from yumnews.services.preregistration import PreregistrationService

    service = PreregistrationService()
    state = {}
    if request.method == "POST":
        if not current_user.is_authenticated:
            return redirect(
                url_for("auth.login", next=url_for("public.preregistration"))
            )
        action = request.form.get("action")
        if action not in ("join", "leave") or (
            action == "join" and request.form.get("consent") != "yes"
        ):
            flash("Cochez votre accord pour recevoir le message d’ouverture.", "error")
            return redirect(url_for("public.preregistration"))
        with container().db.session_scope() as session:
            service.set_status(session, current_user.id, action == "join")
        flash(
            "Votre préinscription est enregistrée. Aucun paiement ne sera effectué."
            if action == "join"
            else "Vous avez quitté la liste de préinscription.",
            "success",
        )
        return redirect(url_for("public.preregistration"))
    if current_user.is_authenticated:
        with container().db.session_scope() as session:
            state = service.status(session, current_user.id)
    return render_template("public/preregistration.html", preregistration=state)
