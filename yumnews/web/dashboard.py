from __future__ import annotations

from flask import Blueprint, abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from yumnews.repositories import (
    InvoiceRepository,
    PassphraseRepository,
    PaymentRepository,
)
from yumnews.services.errors import DomainError
from yumnews.web.context import container, current_policy, db_session
from yumnews.web.forms import ChangePasswordForm

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/app")
@login_required
def app():
    c = container()
    return render_template(
        "dashboard/app.html",
        tmdb_ready=c.tmdb.configured,
        preferences=c.preferences.get(db_session(), current_user.id),
        preference_options=c.preferences.options(current_policy()),
    )  # [Sol]


@dashboard_bp.route("/compte", methods=["GET", "POST"])
@login_required
def account():
    c = container()
    session = db_session()
    entity = current_user.entity
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            with c.db.session_scope() as tx:
                c.auth.change_password(
                    tx, entity, form.current.data, form.password.data
                )
            flash("Mot de passe modifié.", "success")
            return redirect(url_for("dashboard.account"))
        except DomainError as exc:
            flash(exc.message, "error")
    passphrase = PassphraseRepository(session).active_for_user(
        entity.id
    )  # seed premium Discord (client rabatteur)
    return render_template(
        "dashboard/account.html",
        form=form,
        subscription=c.subscriptions.summary(session, entity),
        invoices=InvoiceRepository(session).for_user(entity.id),
        payments=PaymentRepository(session).for_user(entity.id)[:10],
        follows=c.members.follows(session, entity),
        watchlist=c.members.watchlist(session, entity),
        policy=current_policy(),
        discord_seed=passphrase.phrase if passphrase else None,
    )


@dashboard_bp.get("/compte/factures/<number>")
@login_required
def invoice(number: str):
    session = db_session()
    invoice = InvoiceRepository(session).by_number_for_user(number, current_user.id)
    if invoice is None:
        abort(404)
    return render_template(
        "dashboard/invoice.html",
        invoice=invoice,
        user=current_user.entity,
        snapshot=InvoiceRepository(session).snapshot(invoice.id),
    )  # [Sol]
