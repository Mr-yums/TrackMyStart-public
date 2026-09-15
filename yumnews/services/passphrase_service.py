"""Passphrases Discord : émission à la redemption d'un code rabatteur, validation par le bot.

Le bot Discord n'existe pas encore ; cette couche est prête pour lui. Côté produit :
- ``issue_for`` est appelé par ``CouponService`` quand un paiement via rabatteur réussit ;
- ``claim`` sera appelé par le bot (via une commande CLI ou un futur endpoint HTTP signé)
  pour valider la phrase collée par le client, une seule fois.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from yumnews.domain.models import DiscordPassphrase, Redemption, User, utcnow
from yumnews.repositories import PassphraseRepository
from yumnews.services.passphrase import generate_seed


class PassphraseService:
    def __init__(self, ttl_days: int | None = None) -> None:
        # None = pas d'expiration (le client garde sa phrase tant qu'il n'a pas rejoint le Discord).
        self.ttl_days = ttl_days

    def issue_for(
        self,
        session: Session,
        user: User,
        affiliate_id: int | None,
        redemption: Redemption,
    ) -> DiscordPassphrase:
        """Émet (ou réutilise) LA passphrase du client. Une seule active par compte."""
        repo = PassphraseRepository(session)
        existing = repo.active_for_user(user.id)
        if existing is not None:
            return existing
        phrase = generate_seed()
        while (
            repo.by_phrase(phrase) is not None
        ):  # collision quasi impossible, mais on garantit l'unicité
            phrase = generate_seed()
        expires_at = utcnow() + timedelta(days=self.ttl_days) if self.ttl_days else None
        passphrase = DiscordPassphrase(
            user_id=user.id,
            affiliate_id=affiliate_id,
            redemption_id=redemption.id,
            phrase=phrase,
            expires_at=expires_at,
        )
        return repo.add(passphrase)

    def claim(self, session: Session, phrase: str) -> DiscordPassphrase | None:
        """Valide une phrase collée par un client. Usage unique ; renvoie None si refusée."""
        return PassphraseRepository(session).claim_once(phrase)
