"""Commandes ``flask`` : init-db, expire-subscriptions, grant-premium, create-admin, check-feeds."""

from __future__ import annotations

import click
from flask import Flask

from yumnews.container import Container


def register_cli(app: Flask, container: Container) -> None:
    # [Sol] Consultation locale uniquement, sans envoi de message.
    @app.cli.command("preregistrations")
    @click.option(
        "--details",
        is_flag=True,
        help="Afficher les adresses et le consentement (données privées).",
    )
    def preregistrations(details: bool) -> None:
        """Compte les préinscriptions Premium actives ; aucun paiement ni mail."""
        import json
        from yumnews.repositories.preference_repository import PreferenceRepository

        with container.db.session_scope() as session:
            rows = PreferenceRepository(session).preregistrations()
            click.echo(
                json.dumps(
                    rows if details else {"active": len(rows)}, ensure_ascii=False
                )
            )

    @app.cli.command("init-db")
    def init_db() -> None:
        """Crée les tables (idempotent)."""
        container.db.create_all()
        click.echo("Tables créées.")

    @app.cli.command("expire-subscriptions")
    def expire_subscriptions() -> None:
        """À lancer chaque nuit (cron) : passe en « expired » les périodes échues."""
        with container.db.session_scope() as session:
            count = container.subscriptions.expire_overdue(session)
        click.echo(f"{count} abonnement(s) expiré(s).")

    @app.cli.command("grant-premium")
    @click.argument("email")
    def grant_premium(email: str) -> None:
        """Offre une période Premium (support, test)."""
        from yumnews.repositories import UserRepository

        with container.db.session_scope() as session:
            user = UserRepository(session).by_email(email)
            if user is None:
                raise click.ClickException("Utilisateur introuvable.")
            sub = container.subscriptions.activate(session, user)
            click.echo(
                f"Premium actif pour {email} jusqu'au {sub.current_period_end:%d/%m/%Y}."
            )

    @app.cli.command("create-user")
    @click.argument("email")
    @click.argument("password")
    @click.option("--name", default="Admin")
    @click.option("--admin", is_flag=True)
    def create_user(email: str, password: str, name: str, admin: bool) -> None:
        with container.db.session_scope() as session:
            user = container.auth.register(session, email, password, name)
            user.email_verified = True
            user.is_admin = admin
        click.echo(f"Utilisateur {email} créé (admin={admin}).")

    @app.cli.command("set-password")
    @click.argument("email")
    @click.argument("password", required=False)
    def set_password(email: str, password: str | None) -> None:
        """Régénère (ou fixe) le mot de passe d'un compte — test/support, usage local.

        Sans argument PASSWORD, un mot de passe aléatoire est généré et affiché.
        Les mots de passe restent hashés en base : on ne peut que les réécrire, jamais les relire.
        """
        import secrets

        from yumnews.repositories import UserRepository

        with container.db.session_scope() as session:
            user = UserRepository(session).by_email(email.strip().lower())
            if user is None:
                raise click.ClickException("Utilisateur introuvable.")
            new_password = password or secrets.token_urlsafe(12)
            if len(new_password) < 8:
                raise click.ClickException(
                    "Mot de passe trop court (8 caractères minimum)."
                )
            user.password_hash = container.auth.hasher.hash(new_password)
        click.echo(f"Mot de passe réécrit pour {email} : {new_password}")

    @app.cli.command("check-feeds")
    def check_feeds() -> None:
        """Teste chaque flux RSS et affiche le nombre d'articles."""
        from yumnews.catalog.news.sources import SOURCES

        for source in SOURCES:
            articles = container.news.feed(source.key, limit=50) or []
            click.echo(
                f"{'OK ' if articles else 'KO '} {source.key:20s} {len(articles):3d}  {source.url}"
            )

    # ---- coupons & rabatteurs --------------------------------
    @app.cli.command("create-affiliate")
    @click.argument("name")
    @click.option("--email", default=None, help="Contact du rabatteur.")
    @click.option(
        "--commission",
        type=int,
        default=None,
        help="Commission en %% (défaut : config).",
    )
    @click.option(
        "--code", default=None, help="Crée aussi son code promo rattaché (prix fixe)."
    )
    @click.option(
        "--price-cents",
        type=int,
        default=1200,
        show_default=True,
        help="Prix fixe du code rabatteur.",
    )
    def create_affiliate(name, email, commission, code, price_cents) -> None:
        """Crée un rabatteur et, si --code est fourni, son coupon prix-fixe (12 € par défaut)."""
        from yumnews.domain.enums import CouponKind
        from yumnews.domain.models import Affiliate, Coupon
        from yumnews.repositories import CouponRepository

        with container.db.session_scope() as session:
            affiliate = Affiliate(
                name=name,
                email=email,
                commission_percent=commission
                if commission is not None
                else container.settings.affiliate_commission_percent,
            )
            session.add(affiliate)
            session.flush()
            click.echo(
                f"Rabatteur #{affiliate.id} « {name} » créé (commission {affiliate.commission_percent} %)."
            )
            if code:
                normalized = CouponRepository.normalize(code)
                if CouponRepository(session).by_code(normalized) is not None:
                    raise click.ClickException(f"Le code {normalized} existe déjà.")
                session.add(
                    Coupon(
                        code=normalized,
                        kind=CouponKind.FIXED,
                        value=price_cents,
                        affiliate_id=affiliate.id,
                    )
                )
                click.echo(
                    f"Code rabatteur {normalized} → {price_cents / 100:.2f} € par mois."
                )

    @app.cli.command("create-coupon")
    @click.argument("code")
    @click.option("--kind", type=click.Choice(["percent", "fixed"]), required=True)
    @click.option(
        "--value",
        type=int,
        required=True,
        help="PERCENT: %% de remise. FIXED: prix final en centimes.",
    )
    @click.option(
        "--affiliate",
        "affiliate_id",
        type=int,
        default=None,
        help="Rattacher à un rabatteur.",
    )
    @click.option(
        "--max-per-user",
        type=int,
        default=None,
        help="Nb max de paiements par compte (ex. 5 = promo 5 mois).",
    )
    @click.option(
        "--max-uses", type=int, default=None, help="Plafond global d'utilisations."
    )
    def create_coupon(code, kind, value, affiliate_id, max_per_user, max_uses) -> None:
        """Crée un coupon générique ou promo (ex. promo découverte : --kind percent --value 20 --max-per-user 5)."""
        from yumnews.domain.enums import CouponKind
        from yumnews.domain.models import Coupon
        from yumnews.repositories import AffiliateRepository, CouponRepository

        with container.db.session_scope() as session:
            normalized = CouponRepository.normalize(code)
            if CouponRepository(session).by_code(normalized) is not None:
                raise click.ClickException(f"Le code {normalized} existe déjà.")
            if (
                affiliate_id is not None
                and AffiliateRepository(session).get(affiliate_id) is None
            ):
                raise click.ClickException(f"Rabatteur #{affiliate_id} introuvable.")
            session.add(
                Coupon(
                    code=normalized,
                    kind=CouponKind(kind),
                    value=value,
                    affiliate_id=affiliate_id,
                    max_periods_per_user=max_per_user,
                    max_redemptions=max_uses,
                )
            )
            click.echo(f"Coupon {normalized} créé ({kind} {value}).")

    @app.cli.command("affiliate-report")
    @click.argument("affiliate_id", type=int, required=False)
    def affiliate_report(affiliate_id) -> None:
        """Clients amenés et commission due. Sans argument : tous les rabatteurs."""
        from yumnews.repositories import AffiliateRepository

        with container.db.session_scope() as session:
            repo = AffiliateRepository(session)
            affiliates = [repo.get(affiliate_id)] if affiliate_id else repo.all()
            if not affiliates or affiliates == [None]:
                raise click.ClickException("Aucun rabatteur.")
            click.echo(
                f"{'#':>3} {'Rabatteur':24} {'Clients':>7} {'Mois payés':>10} {'CA':>9} {'Commission due':>14}"
            )
            for affiliate in affiliates:
                report = repo.report(affiliate.id)
                click.echo(
                    f"{affiliate.id:>3} {affiliate.name[:24]:24} {report.distinct_clients:>7} "
                    f"{report.paid_redemptions:>10} {report.revenue_cents / 100:>7.2f} € "
                    f"{report.commission_cents / 100:>12.2f} €"
                )

    @app.cli.command("claim-passphrase")
    @click.argument("phrase")
    def claim_passphrase(phrase) -> None:
        """Valide une passphrase Discord (usage unique). Sert de test tant que le bot n'existe pas."""
        with container.db.session_scope() as session:
            passphrase = container.passphrases.claim(session, phrase)
        if passphrase is None:
            raise click.ClickException("Passphrase invalide, expirée ou déjà utilisée.")
        click.echo(
            f"Passphrase validée pour le client #{passphrase.user_id} (rabatteur #{passphrase.affiliate_id})."
        )
