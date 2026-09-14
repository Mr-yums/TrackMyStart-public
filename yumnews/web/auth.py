from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from urllib.parse import urlparse

from yumnews.services.auth_service import Credentials
from yumnews.services.errors import DomainError
from yumnews.web.context import AuthenticatedUser, client_ip, container, db_session
from yumnews.web.forms import ForgotForm, LoginForm, RegisterForm, ResetForm

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/inscription", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(_safe_next() or url_for("dashboard.app"))
    form = RegisterForm()
    if form.validate_on_submit():
        try:
            with container().db.session_scope() as session:
                user = container().auth.register(
                    session, form.email.data, form.password.data, form.display_name.data
                )
                session.flush()
                login_user(AuthenticatedUser(user))
            flash("Bienvenue ! Un email de confirmation vous a été envoyé.", "success")
            return redirect(_safe_next() or url_for("dashboard.app"))
        except DomainError as exc:
            flash(exc.message, "error")
    return render_template("auth/register.html", form=form)


@auth_bp.route("/connexion", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_safe_next() or url_for("dashboard.app"))
    form = LoginForm()
    if form.validate_on_submit():
        # Pas de session_scope ici : le compteur d'échecs doit être conservé même quand l'auth échoue.
        session = db_session()
        try:
            user = container().auth.authenticate(
                session, Credentials(form.email.data, form.password.data), client_ip()
            )
            session.commit()
            login_user(AuthenticatedUser(user), remember=form.remember.data)
            return redirect(_safe_next() or url_for("dashboard.app"))
        except DomainError as exc:
            session.commit()
            flash(exc.message, "error")
        except Exception:
            session.rollback()
            raise
    return render_template("auth/login.html", form=form)


@auth_bp.post("/deconnexion")
@login_required
def logout():
    logout_user()
    flash("À bientôt !", "info")
    return redirect(url_for("public.home"))


@auth_bp.get("/verification/<token>")
def verify_email(token: str):
    try:
        with container().db.session_scope() as session:
            container().auth.verify_email(session, token)
        flash("Adresse email confirmée.", "success")
    except DomainError as exc:
        flash(exc.message, "error")
    return redirect(
        url_for("dashboard.app")
        if current_user.is_authenticated
        else url_for("auth.login")
    )


@auth_bp.post("/verification/renvoyer")
@login_required
def resend_verification():
    container().auth.send_verification(current_user.entity)
    flash("Email de confirmation renvoyé.", "info")
    return redirect(url_for("dashboard.account"))


@auth_bp.route("/mot-de-passe-oublie", methods=["GET", "POST"])
def forgot_password():
    form = ForgotForm()
    if form.validate_on_submit():
        with container().db.session_scope() as session:
            container().auth.request_password_reset(session, form.email.data)
        flash(
            "Si un compte actif correspond à cette adresse, vous recevrez un lien de réinitialisation. Vérifiez aussi les indésirables.",
            "info",
        )
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot.html", form=form)


@auth_bp.route("/reinitialiser/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    form = ResetForm()
    if form.validate_on_submit():
        try:
            with container().db.session_scope() as session:
                container().auth.reset_password(session, token, form.password.data)
            flash("Mot de passe mis à jour, connectez-vous.", "success")
            return redirect(url_for("auth.login"))
        except DomainError as exc:
            flash(exc.message, "error")
    return render_template("auth/reset.html", form=form, token=token)


def _safe_next() -> str | None:
    target = request.args.get("next") or request.form.get("next")
    if (
        target
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not any(ord(c) < 32 or ord(c) == 127 for c in target)
        and not urlparse(target).netloc
        and not urlparse(target).scheme
    ):  # [Sol] URL locale non ambiguë.
        return target
    return None
