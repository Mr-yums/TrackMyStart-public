"""[Sol] Statuts personnels et filtres Premium ; aucun cache partagé modifié."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import re

from yumnews.repositories.preference_repository import PreferenceRepository
from yumnews.services.errors import ValidationError

FILTERS = {
    "country": "",
    "runtime_min": None,
    "runtime_max": None,
    "votes_min": None,
    "hide_seen": False,
    "hide_disliked": False,
}
DEFAULT = {
    "filters": {"movie": deepcopy(FILTERS), "tv": deepcopy(FILTERS)},
    "titles": {},
}
# Sélection explicite de codes ISO ; la liste affichée et la validation sont communes.
COUNTRIES = {
    "FR": "France",
    "US": "États-Unis",
    "GB": "Royaume-Uni",
    "DE": "Allemagne",
    "ES": "Espagne",
    "IT": "Italie",
    "CA": "Canada",
    "JP": "Japon",
    "KR": "Corée du Sud",
    "IN": "Inde",
    "AU": "Australie",
    "BE": "Belgique",
    "CH": "Suisse",
    "CN": "Chine",
    "BR": "Brésil",
    "MX": "Mexique",
    "SE": "Suède",
    "DK": "Danemark",
    "NO": "Norvège",
}


class CatalogPreferences:
    def get(self, session, uid):
        return (
            deepcopy(PreferenceRepository(session).get(uid).get("catalog", DEFAULT))
            if uid
            else deepcopy(DEFAULT)
        )

    def save_filters(self, session, uid, policy, kind, payload):
        policy.require("advanced_filters")
        if (
            kind not in ("movie", "tv")
            or not isinstance(payload, dict)
            or set(payload) - set(FILTERS)
        ):
            raise ValidationError("Filtres invalides.")
        values = deepcopy(FILTERS)
        values.update(payload)
        if not isinstance(values["country"], str) or values["country"] not in (
            "",
            *COUNTRIES,
        ):
            raise ValidationError("Pays de production inconnu.")
        for field, maximum in [
            ("runtime_min", 1000),
            ("runtime_max", 1000),
            ("votes_min", 100000000),
        ]:
            value = values[field]
            if value is not None and (
                type(value) is not int or not 0 <= value <= maximum
            ):
                raise ValidationError("Durée ou nombre de votes invalide.")
        if (
            values["runtime_min"] is not None
            and values["runtime_max"] is not None
            and values["runtime_min"] > values["runtime_max"]
        ):
            raise ValidationError("La durée minimale dépasse la durée maximale.")
        if any(type(values[f]) is not bool for f in ("hide_seen", "hide_disliked")):
            raise ValidationError("Option de masquage invalide.")

        def update(doc):
            data = deepcopy(doc.get("catalog", DEFAULT))
            data["filters"][kind] = values
            doc["catalog"] = data

        PreferenceRepository(session).mutate(uid, update)
        return values

    def mark(self, session, uid, kind, media_id, payload):
        if (
            kind not in ("movie", "tv")
            or not re.fullmatch(r"[1-9][0-9]{0,9}", str(media_id))
            or not isinstance(payload, dict)
            or set(payload) - {"seen", "disliked", "title"}
        ):
            raise ValidationError("Titre ou statut invalide.")
        if not any(k in payload for k in ("seen", "disliked")) or any(
            type(payload[k]) is not bool for k in ("seen", "disliked") if k in payload
        ):
            raise ValidationError("Statut invalide.")
        if "title" in payload and (
            not isinstance(payload["title"], str) or len(payload["title"]) > 300
        ):
            raise ValidationError("Libellé invalide.")
        result = {}

        def update(doc):
            data = deepcopy(doc.get("catalog", DEFAULT))
            key = f"{kind}:{media_id}"
            value = {
                **data["titles"].get(key, {"seen": False, "disliked": False}),
                **payload,
            }
            if value["seen"] or value["disliked"]:
                if key not in data["titles"] and len(data["titles"]) >= 2000:
                    raise ValidationError(
                        "Limite de 2 000 titres atteinte. Retirez un ancien statut pour continuer."
                    )
                data["titles"][key] = value
            else:
                data["titles"].pop(key, None)
            doc["catalog"] = data
            result.update(value)

        PreferenceRepository(session).mutate(uid, update)
        return result

    @staticmethod
    def visible(items, data, policy):
        if not policy.can("hide_titles"):
            return list(items)
        out = []
        for item in items:
            kind = item.get("media_type")
            f = data["filters"].get(kind, {})
            status = data["titles"].get(f"{kind}:{item.get('id')}", {})
            if (f.get("hide_seen") and status.get("seen")) or (
                f.get("hide_disliked") and status.get("disliked")
            ):
                continue
            out.append(item)
        return out

    def filter(self, items, data, policy, kind, tmdb):
        items = self.visible(items, data, policy)
        if not policy.can("advanced_filters"):
            return items
        f = data["filters"][kind]
        if f["votes_min"] is not None:
            items = [i for i in items if i.get("votes", 0) >= f["votes_min"]]
        if not f["country"] and f["runtime_min"] is None and f["runtime_max"] is None:
            return items

        # Métadonnées légères, cache TMDB et parallélisme borné. Une panne remonte
        # explicitement : ne pas inventer un résultat vide ou filtrer par langue.
        def matches(item):
            metadata = tmdb.filter_metadata(kind, item["id"])
            if f["country"] and f["country"] not in metadata["production_countries"]:
                return False
            runtime = metadata["runtime"]
            if f["runtime_min"] is not None and (
                runtime is None or runtime < f["runtime_min"]
            ):
                return False
            if f["runtime_max"] is not None and (
                runtime is None or runtime > f["runtime_max"]
            ):
                return False
            return True

        with ThreadPoolExecutor(max_workers=6) as pool:
            keep = list(pool.map(matches, items))
        return [i for i, valid in zip(items, keep) if valid]
