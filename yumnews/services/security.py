"""Hachage des mots de passe et jetons signés (vérification email, reset)."""

from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

# Hash factice utilisé quand l'email n'existe pas, pour un temps de réponse constant.
_DUMMY_HASH = generate_password_hash("yumnews-dummy-password", method="scrypt")


class PasswordHasher:
    method = "scrypt"

    def hash(self, password: str) -> str:
        return generate_password_hash(password, method=self.method)

    def verify(self, password: str, password_hash: str | None) -> bool:
        if not password_hash:
            check_password_hash(_DUMMY_HASH, password)
            return False
        return check_password_hash(password_hash, password)


class TokenService:
    """Jetons horodatés et signés, un « salt » par usage (pas de table en base)."""

    def __init__(self, secret_key: str) -> None:
        self._serializer = URLSafeTimedSerializer(secret_key)

    def issue(self, purpose: str, payload: dict) -> str:
        return self._serializer.dumps(payload, salt=f"yumnews:{purpose}")

    def read(self, purpose: str, token: str, max_age: int) -> dict | None:
        try:
            return self._serializer.loads(
                token, salt=f"yumnews:{purpose}", max_age=max_age
            )
        except (BadSignature, SignatureExpired):
            return None
