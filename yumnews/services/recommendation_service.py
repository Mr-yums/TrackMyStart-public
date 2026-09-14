"""[Sol] Fil explicable : suivis prioritaires, retours explicites, découverte bornée."""

from copy import deepcopy
from datetime import date

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from yumnews.editorial.stories import STORIES
from yumnews.repositories.preference_repository import PreferenceRepository
from yumnews.services.errors import ValidationError

TOPICS = {
    "project": "Projets et sorties",
    "casting": "Castings",
    "television": "Rendez-vous TV",
    "netflix": "Netflix",
    "prime": "Prime Video",
    "cinema": "Cinéma",
    "series": "Séries",
}
DEFAULT = {"enabled": True, "muted": [], "feedback": {}}
# Métadonnées éditoriales explicites ; aucun invité TV déduit d'un programme général.
METADATA = {
    "netflix-lust-stories-3-septembre": (
        ["project", "netflix", "cinema"],
        [
            "Radhika Apte",
            "Konkona Sen Sharma",
            "Aditi Rao Hydari",
            "Vijay Varma",
            "Vikramaditya Motwane",
            "Kiran Rao",
            "Shakun Batra",
            "Vishal Bhardwaj",
        ],
    ),
    "kathryn-newton-comedie-mike-birbiglia": (
        ["casting", "cinema"],
        ["Kathryn Newton", "Mike Birbiglia", "Lucas Hedges", "Geraldine Viswanathan"],
    ),
    "c-a-vous-rendez-vous-culture-rentree": (["television"], []),
    "prime-video-neagley-maria-sten": (["project", "prime", "series"], ["Maria Sten"]),
}


class RecommendationService:
    def __init__(self, secret_key):
        self.signer = URLSafeTimedSerializer(secret_key, salt="sol-recommendations-v1")

    def settings(self, session, uid):
        raw = PreferenceRepository(session).get(uid).get("recommendations", {})
        return {**deepcopy(DEFAULT), **deepcopy(raw)}

    def change(self, session, uid, payload):
        if (
            not isinstance(payload, dict)
            or not payload
            or set(payload) - {"enabled", "muted", "reset", "remove"}
        ):
            raise ValidationError("Réglage de recommandation invalide.")
        if "enabled" in payload and type(payload["enabled"]) is not bool:
            raise ValidationError("Activation invalide.")
        if "muted" in payload and (
            not isinstance(payload["muted"], list)
            or len(payload["muted"]) > len(TOPICS)
            or any(not isinstance(k, str) or k not in TOPICS for k in payload["muted"])
        ):
            raise ValidationError("Sujet inconnu.")
        if "reset" in payload and payload["reset"] is not True:
            raise ValidationError("Réinitialisation invalide.")
        if "remove" in payload and not isinstance(payload["remove"], str):
            raise ValidationError("Retour invalide.")

        def edit(document):
            state = {**deepcopy(DEFAULT), **document.get("recommendations", {})}
            if payload.get("reset"):
                state = deepcopy(DEFAULT)
            for key in ("enabled", "muted"):
                if key in payload:
                    state[key] = payload[key]
            if "remove" in payload:
                state["feedback"].pop(payload["remove"], None)
            document["recommendations"] = state

        PreferenceRepository(session).mutate(uid, edit)
        return self.settings(session, uid)

    def feedback(self, session, uid, payload):
        if (
            not isinstance(payload, dict)
            or set(payload) != {"token", "action"}
            or payload["action"] not in ("more", "less", "hide")
            or not isinstance(payload["token"], str)
            or len(payload["token"]) > 4000
        ):
            raise ValidationError("Retour invalide.")
        try:
            item = self.signer.loads(payload["token"], max_age=7 * 86400)
        except (BadSignature, SignatureExpired):
            raise ValidationError("Rechargez le fil avant de donner votre avis.")
        if item.get("user") != uid:
            raise ValidationError("Ce contenu appartient à un autre fil.")

        def edit(document):
            state = {**deepcopy(DEFAULT), **document.get("recommendations", {})}
            if item["id"] not in state["feedback"] and len(state["feedback"]) >= 200:
                raise ValidationError(
                    "Supprimez quelques anciens retours dans les réglages du fil."
                )
            state["feedback"][item["id"]] = {
                "action": payload["action"],
                "title": item["title"],
                "topics": item["topics"],
            }
            document["recommendations"] = state

        PreferenceRepository(session).mutate(uid, edit)

    def candidates(self, catalog, policy, follows, today):
        names = {f.name.casefold(): f.name for f in follows}
        people = {f.person_id: f.name for f in follows}
        feed = catalog.person_feed(policy, list(people))
        candidates = []
        for item in feed["upcoming"] + feed["recent"]:
            person = item.get("person", {})
            if person.get("id") not in people:
                continue
            kind = item["media_type"]
            candidates.append(
                {
                    "id": f"{kind}:{item['id']}",
                    "kind": "project",
                    "title": item["title"],
                    "topics": ["project", "series" if kind == "tv" else "cinema"],
                    "date": item["date"],
                    "people": [people[person["id"]]],
                    "media": item,
                    "confidence": 2,
                    "status": "Date catalogue TMDB · disponibilité France à vérifier",
                    "source": "TMDB",
                }
            )
        for story in STORIES:
            published = date.fromisoformat(story["published_at"])
            if not 0 <= (today - published).days <= 90:
                continue
            topics, cast = METADATA[story["slug"]]
            matched = [names[n.casefold()] for n in cast if n.casefold() in names]
            candidates.append(
                {
                    "id": "story:" + story["slug"],
                    "kind": "article",
                    "title": story["title"],
                    "topics": topics,
                    "date": story["published_at"],
                    "people": matched,
                    "confidence": 2
                    if story["slug"] == "kathryn-newton-comedie-mike-birbiglia"
                    else 3,
                    "status": story["status"],
                    "source": story["source_name"],
                    "link": "/actualites/" + story["slug"],
                    "description": story["lead"],
                }
            )
        return candidates, bool(feed.get("locked"))

    def feed(
        self,
        session,
        uid,
        catalog,
        policy,
        follows,
        watchlist,
        mode="personal",
        today=None,
    ):
        today = today or date.today()
        state = self.settings(session, uid)
        candidates, locked = self.candidates(catalog, policy, follows, today)
        ranked = rank(
            candidates,
            state,
            {f"{w.media_type}:{w.media_id}" for w in watchlist},
            today,
            chronological=mode == "chronological" or not state["enabled"],
        )
        for item in ranked:
            item["token"] = self.signer.dumps(
                {
                    "user": uid,
                    "id": item["id"],
                    "title": item["title"],
                    "topics": item["topics"],
                }
            )
            item["in_watchlist"] = item["id"] in {
                f"{w.media_type}:{w.media_id}" for w in watchlist
            }
            item["feedback"] = state["feedback"].get(item["id"], {}).get("action")
        return {
            "items": ranked,
            "settings": state,
            "topics": TOPICS,
            "locked": locked,
            "following_count": len(follows),
            "version": "stars-v1",
        }


def rank(candidates, state, watchlist, today, chronological=False, limit=12):
    """[Sol] Pas de popularité ni clic dans le score ; les exclusions gagnent toujours."""
    weights = {topic: 0 for topic in TOPICS}
    for response in state["feedback"].values():
        value = {"more": 1, "less": -1, "hide": 0}[response["action"]]
        for topic in response["topics"]:
            if topic in weights:
                weights[topic] += value
    pool = []
    seen = set()
    for original in candidates:
        item = deepcopy(original)
        feedback = state["feedback"].get(item["id"], {}).get("action")
        if (
            item["id"] in seen
            or feedback == "hide"
            or set(item["topics"]) & set(state["muted"])
        ):
            continue
        seen.add(item["id"])
        followed = bool(item["people"])
        explicit = max(-20, min(20, sum(weights[t] * 4 for t in item["topics"])))
        # Répéter un clic ne peut pas amplifier un signal : un avis remplace le précédent.
        affinity = (
            (100 if followed else 0) + (30 if item["id"] in watchlist else 0) + explicit
        )
        if feedback == "less":
            affinity -= 40
        if chronological:
            affinity = 0
        delta = (date.fromisoformat(item["date"][:10]) - today).days
        freshness = max(0, 10 - abs(delta) / 12)
        item["score"] = round(affinity + freshness + 4 * item.get("confidence", 2), 2)
        item["reason"] = (
            ("Vous suivez " + ", ".join(item["people"]))
            if followed
            else (
                "Dans votre liste"
                if item["id"] in watchlist
                else "Découverte éditoriale sourcée"
            )
        )
        if explicit > 0 and not chronological:
            item["reason"] += " · vos avis favorisent ce sujet"
        if feedback == "less":
            item["reason"] += " · moins souvent demandé"
        pool.append(item)
    if chronological:
        return sorted(pool, key=lambda i: (i["date"], i["id"]), reverse=True)[:limit]
    order = lambda i: (-i["score"], i["id"])
    familiar = sorted(
        [i for i in pool if i["people"] or i["id"] in watchlist], key=order
    )
    discovery = sorted(
        [i for i in pool if not i["people"] and i["id"] not in watchlist], key=order
    )
    if not familiar:
        # Démarrage à froid : honnêtement éditorial, aucun goût inventé.
        return discovery[:limit]
    result = []
    counts = {}
    for item in familiar:
        key = tuple(item["people"])
        if counts.get(key, 0) >= 3:
            continue
        counts[key] = counts.get(key, 0) + 1
        result.append(item)
        if len(result) >= limit - limit // 5:
            break
    # Maximum 20 % de découvertes lorsque des suivis sont disponibles ; jamais de remplissage forcé.
    allowance = min(limit // 5, len(result) // 4)
    for item in discovery[:allowance]:
        result.insert(min(4 + 5 * discovery.index(item), len(result)), item)
    return result[:limit]
