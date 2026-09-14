"""Inscription, connexion, vérification email, réinitialisation du mot de passe."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from yumnews.domain.models import User, utcnow
from yumnews.repositories import LoginAttemptRepository, UserRepository
from yumnews.services.errors import AuthenticationError, ThrottledError, ValidationError
from yumnews.services.mailer import Email, Mailer
from yumnews.services.security import PasswordHasher, TokenService

MIN_PASSWORD_LENGTH = 8
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
VERIFY_TOKEN_MAX_AGE = 60 * 60 * 48
RESET_TOKEN_MAX_AGE = 60 * 60


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


class AuthService:
    def __init__(
        self,
        hasher: PasswordHasher,
        tokens: TokenService,
        mailer: Mailer,
        site_url: str,
        site_name: str = "TrackMyStart",
    ) -> None:
        self.hasher = hasher
        self.tokens = tokens
        self.mailer = mailer
        self.site_url = site_url
        self.site_name = site_name

    # ---- inscription -------------------------------------------------
    def register(
        self, session: Session, email: str, password: str, display_name: str
    ) -> User:
        email = self._normalize_email(email)
        self._check_password(password)
        display_name = display_name.strip()
        if not (2 <= len(display_name) <= 40):
            raise ValidationError("Le pseudo doit faire entre 2 et 40 caractères.")
        if not re.fullmatch(r"[\w\- .'’]+", display_name):
            raise ValidationError("Le pseudo contient des caractères non autorisés.")

        users = UserRepository(session)
        if users.by_email(email):
            raise ValidationError("Un compte existe déjà avec cet email.")
        user = User(
            email=email,
            password_hash=self.hasher.hash(password),
            display_name=display_name,
        )
        try:
            with session.begin_nested():
                users.add(user)
        except IntegrityError:
            raise ValidationError("Un compte existe déjà avec cet email.") from None
        self.send_verification(user)
        return user

    def send_verification(self, user: User) -> None:
        token = self.tokens.issue("verify-email", {"uid": user.id})
        link = f"{self.site_url}/verification/{token}"
        self.mailer.send(
            Email(
                to=user.email,
                category="acces",  # [Sol] Les réponses vont au canal accès.
                subject=f"{self.site_name} — confirmez votre adresse",
                text=f"Bienvenue {user.display_name} !\n\nConfirmez votre adresse : {link}\n\nCe lien expire dans 48 h.",
            )
        )

    def verify_email(self, session: Session, token: str) -> User:
        data = self.tokens.read("verify-email", token, VERIFY_TOKEN_MAX_AGE)
        if not data:
            raise ValidationError("Lien de vérification invalide ou expiré.")
        user = UserRepository(session).get(int(data["uid"]))
        if user is None:
            raise ValidationError("Compte introuvable.")
        user.email_verified = True
        session.flush()
        return user

    # ---- connexion ---------------------------------------------------
    def authenticate(
        self, session: Session, credentials: Credentials, ip_address: str
    ) -> User:
        email = self._normalize_email(credentials.email, strict=False)
        attempts = LoginAttemptRepository(session)
        now = utcnow()
        attempt = attempts.find(email, ip_address)
        if attempt and attempt.locked_until and attempt.locked_until > now:
            remaining = int((attempt.locked_until - now).total_seconds() // 60) + 1
            raise ThrottledError(f"Trop de tentatives. Réessayez dans {remaining} min.")

        user = UserRepository(session).by_email(email)
        ok = self.hasher.verify(
            credentials.password, user.password_hash if user else None
        )
        if not ok or user is None or not user.is_active:
            attempt = attempts.get_or_create(email, ip_address)
            attempt.failed_count += 1
            attempt.last_failed_at = now
            if attempt.failed_count >= MAX_FAILED_ATTEMPTS:
                attempt.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                attempt.failed_count = 0
            session.flush()
            raise AuthenticationError("Email ou mot de passe incorrect.")

        if attempt:
            attempts.delete(attempt)
        user.last_login_at = now
        session.flush()
        return user

    # ---- mot de passe oublié -----------------------------------------
    def request_password_reset(self, session: Session, email: str) -> None:
        """Toujours silencieux : ne révèle pas si l'email existe."""
        try:
            email = self._normalize_email(email, strict=False)
        except ValidationError:
            return
        user = UserRepository(session).by_email(email)
        if user is None:
            return
        token = self.tokens.issue(
            "reset-password", {"uid": user.id, "h": user.password_hash[-16:]}
        )
        link = f"{self.site_url}/reinitialiser/{token}"
        self.mailer.send(
            Email(
                to=user.email,
                category="acces",  # [Sol] Les réponses vont au canal accès.
                subject=f"{self.site_name} — réinitialisation du mot de passe",
                text=f"Pour choisir un nouveau mot de passe : {link}\n\nCe lien expire dans 1 h. Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
            )
        )

    def reset_password(self, session: Session, token: str, new_password: str) -> User:
        data = self.tokens.read("reset-password", token, RESET_TOKEN_MAX_AGE)
        if not data:
            raise ValidationError("Lien invalide ou expiré.")
        user = UserRepository(session).get(int(data["uid"]))
        # Le jeton embarque la fin du hash courant : il devient inutilisable après usage.
        if user is None or user.password_hash[-16:] != data.get("h"):
            raise ValidationError("Lien invalide ou déjà utilisé.")
        self._check_password(new_password)
        # [Sol] Le test et le remplacement restent atomiques face à deux sessions concurrentes.
        if not UserRepository(session).replace_password(
            user, user.password_hash, self.hasher.hash(new_password)
        ):
            raise ValidationError("Lien invalide ou déjà utilisé.")
        session.flush()
        return user

    def change_password(
        self, session: Session, user: User, current: str, new_password: str
    ) -> None:
        if not self.hasher.verify(current, user.password_hash):
            raise AuthenticationError("Mot de passe actuel incorrect.")
        self._check_password(new_password)
        user.password_hash = self.hasher.hash(new_password)
        session.flush()

    # ---- helpers -----------------------------------------------------
    @staticmethod
    def _normalize_email(email: str, strict: bool = True) -> str:
        email = (email or "").strip().lower()
        if not email or len(email) > 255:
            raise ValidationError("Adresse email invalide.")
        try:
            validate_email(email, check_deliverability=False)
        except EmailNotValidError:
            if strict:
                raise ValidationError("Adresse email invalide.") from None
        return email

    @staticmethod
    def _check_password(password: str) -> None:
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Le mot de passe doit faire au moins {MIN_PASSWORD_LENGTH} caractères."
            )
        if len(password) > 128:
            raise ValidationError("Mot de passe trop long.")
