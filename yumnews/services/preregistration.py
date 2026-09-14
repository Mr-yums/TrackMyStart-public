"""[Sol] Intention Premium persistante, révocable, sans paiement ni activation."""

from datetime import datetime, timezone
from yumnews.repositories.preference_repository import PreferenceRepository

CONSENT = "Me prévenir par e-mail lorsque les inscriptions Premium ouvriront."


class PreregistrationService:
    def status(self, session, user_id):
        return (
            PreferenceRepository(session)
            .get(user_id)
            .get("premium_preregistration", {})
        )

    def set_status(self, session, user_id, active):
        repo = PreferenceRepository(session)
        # [Sol] Même mutation atomique que les autres espaces de préférences.
        result = {}

        def change(settings):
            previous = settings.get("premium_preregistration", {})
            if previous.get("active", False) == active:
                result.update(previous)
                return
            state = {
                "active": active,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "consent_version": "2026-09-11",
                "consent": CONSENT if active else None,
            }
            settings["premium_preregistration"] = state
            result.update(state)

        repo.mutate(user_id, change)
        return result
