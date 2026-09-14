"""[Sol] Persistance isolée des préférences utilisateur."""

from sqlalchemy.orm import Session
from sqlalchemy import update, select
from copy import deepcopy
from yumnews.domain.models import User, UserPreferences


class PreferenceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: int) -> dict:
        # [Sol] Une lecture ne verrouille pas le compte pendant les appels catalogue.
        row = self.session.get(UserPreferences, user_id)
        return dict(row.settings) if row else {}

    def save(self, user_id: int, settings: dict) -> None:
        row = self.session.get(UserPreferences, user_id)
        if row is None:
            row = UserPreferences(user_id=user_id)
            self.session.add(row)
        row.settings = dict(settings)
        self.session.flush()

    def mutate(self, user_id: int, callback) -> None:
        """[Sol] Sérialiser les écritures JSON, y compris la première création SQLite/PG."""
        self.session.execute(update(User).where(User.id == user_id).values(id=user_id))
        self.session.expire_all()
        document = deepcopy(self.get(user_id))
        callback(document)
        self.save(user_id, document)

    def preregistrations(self) -> list[dict]:
        """[Sol] Liste réservée à la CLI, limitée aux consentements actifs."""
        rows = self.session.execute(
            select(User, UserPreferences).join(
                UserPreferences, UserPreferences.user_id == User.id
            )
        )
        result = []
        for user, preferences in rows:
            state = (preferences.settings or {}).get("premium_preregistration", {})
            if state.get("active") is True:
                result.append(
                    {
                        "email": user.email,
                        "email_verified": user.email_verified,
                        "consent": state.get("consent"),
                        "updated_at": state.get("updated_at"),
                    }
                )
        return result
