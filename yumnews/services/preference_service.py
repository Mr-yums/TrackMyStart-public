"""[Sol] Validation et options de personnalisation, communes à l'API et au dashboard."""

from copy import deepcopy
from yumnews.catalog.news.sources import CATEGORIES, SOURCES_BY_KEY
from yumnews.repositories.preference_repository import PreferenceRepository
from yumnews.services.errors import ValidationError

SECTIONS = {
    "movies": "Films",
    "series": "Séries",
    "mangas": "Mangas",
    "people": "Acteurs",
    "news": "Actualités",
}
TABS = {"home": "Accueil", **SECTIONS, "me": "Mon espace"}
DEFAULTS = {
    "sections": list(SECTIONS),
    "news_categories": ["cinema", "series"],
    "news_sources": [],
    "start_tab": "home",
    "compact_cards": False,
}


class PreferenceService:
    def get(self, session, user_id: int | None) -> dict:
        values = deepcopy(DEFAULTS)
        if user_id is not None:
            values.update(
                {
                    k: v
                    for k, v in PreferenceRepository(session).get(user_id).items()
                    if k in DEFAULTS
                }
            )
        return values

    def save(self, session, user_id: int, payload: dict) -> dict:
        if not isinstance(payload, dict) or set(payload) - set(DEFAULTS):
            raise ValidationError("Préférences inconnues.")
        values = self.get(session, user_id)
        for field, allowed in [
            ("sections", SECTIONS),
            ("news_categories", CATEGORIES),
            ("news_sources", SOURCES_BY_KEY),
        ]:
            if field not in payload:
                continue
            selection = payload[field]
            if (
                not isinstance(selection, list)
                or len(selection) > len(allowed)
                or any(not isinstance(v, str) or v not in allowed for v in selection)
            ):
                raise ValidationError("Sélection invalide : " + field)
            if field in ("sections", "news_categories") and not selection:
                raise ValidationError(
                    "Choisissez au moins une rubrique et un thème de presse."
                )
            values[field] = list(dict.fromkeys(selection))
        if "start_tab" in payload:
            if (
                not isinstance(payload["start_tab"], str)
                or payload["start_tab"] not in TABS
            ):
                raise ValidationError("Onglet d'ouverture invalide.")
            values["start_tab"] = payload["start_tab"]
        if "compact_cards" in payload:
            if type(payload["compact_cards"]) is not bool:
                raise ValidationError("Affichage compact invalide.")
            values["compact_cards"] = payload["compact_cards"]

        # [Sol] Fusionner seulement les champs soumis, sous verrou, pour éviter les pertes concurrentes.
        def change(document):
            document.update({key: values[key] for key in payload})
            values.update(
                {key: value for key, value in document.items() if key in DEFAULTS}
            )

        PreferenceRepository(session).mutate(user_id, change)
        return values

    @staticmethod
    def options(policy) -> dict:
        return {
            "sections": SECTIONS,
            "tabs": TABS,
            "categories": [
                {
                    "key": k,
                    "label": label,
                    "locked": not policy.news_category_allowed(k),
                }
                for k, label in CATEGORIES.items()
            ],
            "sources": [
                {
                    "key": s.key,
                    "name": s.name,
                    "category": s.category,
                    "locked": not policy.news_category_allowed(s.category),
                }
                for s in SOURCES_BY_KEY.values()
            ],
        }
