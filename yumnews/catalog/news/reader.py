"""[Sol] Instantané signé d'un extrait RSS : lecture sans dépendre du cache du flux."""

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit
from itsdangerous import URLSafeSerializer, BadSignature
from yumnews.catalog.news.sources import SOURCES_BY_KEY
from yumnews.editorial.stories import STORIES


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.suppressed = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.suppressed += 1
        if not self.suppressed and tag in ("p", "br", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.suppressed = max(0, self.suppressed - 1)
        if not self.suppressed and tag in ("p", "div", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def excerpt(markup):
    parser = PlainText()
    parser.feed(str(markup or "")[:100000])
    words = re.sub(r"\s+", " ", "".join(parser.parts)).strip().split()
    # Extrait fourni par le média, jamais présenté comme une synthèse originale.
    text = " ".join(words[:180])
    return text[:2400] + ("…" if len(words) > 180 or len(text) > 2400 else "")


def web_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in ("https", "http")
            and bool(parsed.hostname)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


class PressReader:
    def __init__(self, secret):
        self.signer = URLSafeSerializer(secret, salt="sol-press-reader-v1")

    def link(self, article, body):
        for story in STORIES:
            if story["source_url"].rstrip("/") == article["link"].rstrip("/"):
                return "/actualites/" + story["slug"]
        payload = {
            "source": article["source"]["key"],
            "title": article["title"][:300],
            "text": excerpt(body),
            "url": article["link"][:2000],
            "date": article["date"],
            "author": str(article.get("author") or "")[:150],
        }
        return "/lecture/" + self.signer.dumps(payload)

    def read(self, token):
        if len(token) > 8000:
            return None
        try:
            article = self.signer.loads(token)
        except BadSignature:
            return None
        if (
            not isinstance(article, dict)
            or article.get("source") not in SOURCES_BY_KEY
            or not web_url(article.get("url"))
        ):
            return None
        return article
