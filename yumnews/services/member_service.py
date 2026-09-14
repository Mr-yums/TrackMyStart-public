"""Espace membre : acteurs suivis et liste personnelle, avec quotas du plan."""

from __future__ import annotations

from sqlalchemy.orm import Session

from yumnews.domain.models import Follow, User, WatchlistItem
from yumnews.repositories import FollowRepository, WatchlistRepository, UserRepository
from yumnews.services.access_policy import AccessPolicy
from yumnews.services.errors import NotFoundError, ValidationError


class MemberService:
    # ---- follows -----------------------------------------------------
    def follows(self, session: Session, user: User) -> list[Follow]:
        return FollowRepository(session).for_user(user.id)

    def follow(
        self, session: Session, user: User, policy: AccessPolicy, person: dict
    ) -> Follow:
        policy.require("follows")
        UserRepository(session).lock(
            user.id
        )  # [Sol] Quota et insertion dans la même section protégée.
        repo = FollowRepository(session)
        try:
            person_id = int(person.get("id"))
        except (TypeError, ValueError):
            raise ValidationError("Identifiant de personne invalide.") from None
        existing = repo.find(user.id, person_id)
        if existing:
            return existing
        policy.check_quota("follows", repo.count_for_user(user.id))
        follow = Follow(
            user_id=user.id,
            person_id=person_id,
            name=str(person.get("name") or "")[:255] or "Inconnu",
            profile_path=(person.get("profile") or None),
            department=(person.get("department") or None),
        )
        return repo.add(follow)

    def unfollow(self, session: Session, user: User, person_id: int) -> None:
        repo = FollowRepository(session)
        follow = repo.find(user.id, person_id)
        if follow is None:
            raise NotFoundError("Personne non suivie.")
        repo.delete(follow)

    # ---- watchlist ---------------------------------------------------
    def watchlist(self, session: Session, user: User) -> list[WatchlistItem]:
        return WatchlistRepository(session).for_user(user.id)

    def add_to_watchlist(
        self, session: Session, user: User, policy: AccessPolicy, item: dict
    ) -> WatchlistItem:
        policy.require("watchlist")
        UserRepository(session).lock(
            user.id
        )  # [Sol] Deux onglets ne peuvent dépasser le quota.
        media_type = str(item.get("media_type") or "")
        media_id = str(item.get("id") or "")
        if media_type not in ("movie", "tv", "manga") or not media_id:
            raise ValidationError("Élément invalide.")
        repo = WatchlistRepository(session)
        existing = repo.find(user.id, media_type, media_id)
        if existing:
            return existing
        policy.check_quota("watchlist", repo.count_for_user(user.id))
        entry = WatchlistItem(
            user_id=user.id,
            media_type=media_type,
            media_id=media_id,
            title=str(item.get("title") or "")[:255] or "Sans titre",
            poster=item.get("poster") or None,
            year=str(item.get("year") or "")[:8] or None,
        )
        return repo.add(entry)

    def remove_from_watchlist(
        self, session: Session, user: User, media_type: str, media_id: str
    ) -> None:
        repo = WatchlistRepository(session)
        entry = repo.find(user.id, media_type, media_id)
        if entry is None:
            raise NotFoundError("Élément absent de la liste.")
        repo.delete(entry)
