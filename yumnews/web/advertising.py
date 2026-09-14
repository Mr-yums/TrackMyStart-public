"""[Sol] Administration réservée aux administrateurs et annonces selon abonnement."""

from flask import Blueprint, abort, render_template, request
from flask_login import current_user, login_required
from yumnews.web.context import container, current_policy, login_required_json, ok

advertising_bp = Blueprint("advertising", __name__)


@advertising_bp.get("/admin/publicite")
@login_required
def admin():
    if not current_user.is_admin:
        abort(403)
    return render_template("dashboard/advertising.html")


@advertising_bp.route("/api/admin/advertising", methods=["GET", "PUT"])
@login_required_json
def configuration():
    if not current_user.is_admin:
        abort(403)
    service = container().advertising
    if request.method == "PUT":
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            from yumnews.services.errors import ValidationError

            raise ValidationError("Objet JSON attendu.")
        data, revision = service.save(body.get("config"), body.get("revision"))
    else:
        data, revision = service.read()
    return ok(config=data, revision=revision)


@advertising_bp.get("/api/ads/<placement>")
def placement(placement):
    return ok(campaign=container().advertising.placement(current_policy(), placement))


@advertising_bp.after_request
def private(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response
