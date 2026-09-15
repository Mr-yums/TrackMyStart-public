"""Passphrases Discord remises aux clients venus via un rabatteur."""

from __future__ import annotations

from sqlalchemy import or_, select, update

from yumnews.domain.enums import PassphraseStatus
from yumnews.domain.models import DiscordPassphrase, utcnow
from yumnews.repositories.base import Repository


class PassphraseRepository(Repository[DiscordPassphrase]):
    model = DiscordPassphrase

    @staticmethod
    def normalize(phrase: str) -> str:
        return (phrase or "").strip().lower()

    def by_phrase(self, phrase: str) -> DiscordPassphrase | None:
        return self.session.scalar(
            select(DiscordPassphrase).where(
                DiscordPassphrase.phrase == self.normalize(phrase)
            )
        )

    def active_for_user(self, user_id: int) -> DiscordPassphrase | None:
        """La passphrase encore valable d'un client (PENDING), s'il en a déjà une."""
        stmt = select(DiscordPassphrase).where(
            DiscordPassphrase.user_id == user_id,
            DiscordPassphrase.status == PassphraseStatus.PENDING,
        )
        return self.session.scalar(stmt)

    def claim_once(self, phrase: str) -> DiscordPassphrase | None:
        """[Sol] Le prédicat est évalué par la base, même avec un objet ORM périmé."""
        now = utcnow()
        claimed_id = self.session.scalar(
            update(DiscordPassphrase)
            .where(
                DiscordPassphrase.phrase == self.normalize(phrase),
                DiscordPassphrase.status == PassphraseStatus.PENDING,
                or_(
                    DiscordPassphrase.expires_at.is_(None),
                    DiscordPassphrase.expires_at > now,
                ),
            )
            .values(status=PassphraseStatus.CLAIMED, claimed_at=now)
            .returning(DiscordPassphrase.id),
            execution_options={"synchronize_session": False},
        )
        if claimed_id is None:
            return None
        return self.session.get(DiscordPassphrase, claimed_id, populate_existing=True)
