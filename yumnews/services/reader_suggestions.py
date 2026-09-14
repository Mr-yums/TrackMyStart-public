"""[Sol] Presse disponible, classement explicable et pagination stable sans archive fictive."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import re
import time
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from itsdangerous import URLSafeTimedSerializer, BadSignature

from yumnews.catalog.news.sources import SOURCES, SOURCES_BY_KEY
from yumnews.catalog.news.reader import web_url
from yumnews.services.recommendation_service import DEFAULT, TOPICS
from yumnews.services.errors import ValidationError
from yumnews.catalog.http import ApiUnavailable


def normalized(text):
    return re.sub(
        r"\W+",
        " ",
        "".join(
            c
            for c in unicodedata.normalize("NFKD", str(text)).casefold()
            if not unicodedata.combining(c)
        ),
    ).strip()


def canonical(url):
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(sorted(query)),
            "",
        )
    )


def topics(article):
    text = normalized(article["title"] + " " + article.get("description", ""))
    result = set()
    if article["category"] in TOPICS:
        result.add(article["category"])
    for key, words in {
        "netflix": ["netflix"],
        "prime": ["prime video", "amazon prime"],
        "casting": ["casting", "joins", "cast", "rejoindre"],
        "television": ["talk show", "interview", "invite", "emission"],
        "project": ["film", "serie", "series", "movie", "sortie", "release", "projet"],
    }.items():
        if any(" " + word + " " in " " + text + " " for word in words):
            result.add(key)
    return sorted(result)


class ReaderSuggestions:
    def __init__(self, secret):
        self.cursor = URLSafeTimedSerializer(secret, salt="sol-reader-carousel-v1")

    def page(
        self,
        catalog,
        policy,
        prefs,
        settings,
        follows,
        watchlist,
        context,
        uid,
        cursor=None,
    ):
        now = int(time.time() // 900 * 900)
        offset = 0
        previous = None
        if cursor:
            if not isinstance(cursor, str) or len(cursor) > 2000:
                raise ValidationError("Suite de lecture invalide.")
            try:
                previous = self.cursor.loads(cursor, max_age=1800)
            except BadSignature:
                raise ValidationError(
                    "La sélection a expiré. Actualisez les propositions."
                )
            if previous["user"] != uid or previous["context"] != context["url"]:
                raise ValidationError("Suite de lecture invalide.")
            now, offset = previous["at"], previous["offset"]
        chosen = []
        for category in prefs["news_categories"]:
            if not policy.news_category_allowed(category):
                continue
            sources = [
                s
                for s in SOURCES
                if s.category == category
                and (not prefs["news_sources"] or s.key in prefs["news_sources"])
            ]
            # Un choix éditorial de sources prioritaires, sans dépasser le forfait.
            priority = {
                "variety-film": 0,
                "deadline": 0,
                "franceinfo-cinema": 1,
                "variety-tv": 1,
                "premiere": 2,
                "thr-tv": 2,
            }
            sources.sort(key=lambda s: priority.get(s.key, 3))
            chosen.extend(sources[: policy.limits.news_sources_per_category])

        def fetch(source):
            try:
                return (
                    catalog.press.feed(
                        source.key, limit=policy.limits.news_articles_per_source
                    )
                    or []
                )
            except ApiUnavailable:
                return []

        with ThreadPoolExecutor(max_workers=8) as pool:
            batches = list(pool.map(fetch, chosen))
        articles = [item for batch in batches for item in batch]
        ranked = self.rank(articles, settings, follows, watchlist, context, now)
        fingerprint = sha256(
            str([(a["id"], a["score"]) for a in ranked]).encode()
        ).hexdigest()[:24]
        if previous and previous["pool"] != fingerprint:
            return {
                "items": [],
                "next_cursor": None,
                "changed": True,
                "total": len(ranked),
            }
        page = ranked[offset : offset + 12]
        next_cursor = None
        if offset + 12 < len(ranked):
            next_cursor = self.cursor.dumps(
                {
                    "user": uid,
                    "context": context["url"],
                    "pool": fingerprint,
                    "at": now,
                    "offset": offset + 12,
                }
            )
        return {
            "items": page,
            "next_cursor": next_cursor,
            "changed": False,
            "total": len(ranked),
        }

    @staticmethod
    def rank(articles, settings, follows, watchlist, context, now):
        current = canonical(context["url"])
        current_title = normalized(context["title"])
        names = [
            (normalized(f.name), f.name)
            for f in follows
            if len(normalized(f.name)) >= 4
        ]
        titles = [
            (normalized(w.title), w.title)
            for w in watchlist
            if len(normalized(w.title)) >= 5
        ]
        affinity = {k: 0 for k in TOPICS}
        for response in settings["feedback"].values():
            for key in response["topics"]:
                if key in affinity:
                    affinity[key] += {"more": 4, "less": -4, "hide": 0}[
                        response["action"]
                    ]
        result, seen_urls, seen_titles = [], set(), set()
        for a in articles:
            if not a.get("reader_url") or not web_url(a.get("link")):
                continue
            url, title = canonical(a["link"]), normalized(a["title"])
            if (
                url == current
                or title == current_title
                or url in seen_urls
                or title in seen_titles
            ):
                continue
            # Les métadonnées ne transforment jamais une information RSS en annonce confirmée.
            tags = topics(a)
            if set(tags) & set(settings["muted"]):
                continue
            if re.search(
                r"\b(divorce|bikini|scandale intime|vous n allez pas croire)\b", title
            ):
                continue
            aid = "press:" + sha256(url.encode()).hexdigest()[:24]
            feedback = settings["feedback"].get(aid, {}).get("action")
            if feedback == "hide":
                continue
            text = " " + normalized(a["title"] + " " + a.get("description", "")) + " "
            matched = [name for key, name in names if " " + key + " " in text]
            saved = [name for key, name in titles if " " + key + " " in text]
            score = 0
            reason = "À découvrir · " + a["source"]["name"]
            if settings["enabled"]:
                score += min(20, max(-20, sum(affinity[t] for t in tags)))
                if matched:
                    score += 100
                    reason = "Vous suivez " + ", ".join(matched[:2])
                elif saved:
                    score += 35
                    reason = "Dans votre liste : " + saved[0]
                else:
                    overlap = set(normalized(context["title"]).split()) & set(
                        title.split()
                    )
                    overlap = {w for w in overlap if len(w) > 4}
                    score += min(16, len(overlap) * 4)
                    if overlap:
                        reason = "Autour de votre lecture"
                    elif score > 0:
                        reason = "Selon vos avis sur ces sujets"
                if feedback == "less":
                    score -= 40
            try:
                moment = datetime.fromisoformat(a.get("date") or "")
                published = (
                    moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
                ).timestamp()
                if now - published > 90 * 86400 or published - now > 86400:
                    continue
                score = (
                    score + max(0, 10 - max(0, now - published) / 86400)
                    if settings["enabled"]
                    else published
                )
            except ValueError:
                pass
            seen_urls.add(url)
            seen_titles.add(title)
            theme = (
                "netflix"
                if "netflix" in tags
                else "prime"
                if "prime" in tags
                else "television"
                if a["category"] == "series"
                else "cinema"
            )
            result.append(
                {
                    "id": aid,
                    "title": a["title"],
                    "url": a["reader_url"],
                    "image": a.get("image") if web_url(a.get("image")) else None,
                    "source": a["source"]["name"],
                    "reason": reason,
                    "theme": theme,
                    "topics": tags,
                    "score": round(score, 4),
                    "date": a.get("date"),
                }
            )
        result.sort(key=lambda a: (-a["score"], a["id"]))
        if not settings["enabled"]:
            return result
        # Mélanger les médias au premier rang sans jeter leurs autres articles.
        ordered = []
        while result:
            index = next(
                (
                    i
                    for i, a in enumerate(result)
                    if len(ordered) < 2
                    or not (
                        ordered[-1]["source"] == ordered[-2]["source"] == a["source"]
                    )
                ),
                0,
            )
            ordered.append(result.pop(index))
        return ordered
