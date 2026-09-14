"""Agrégateur de presse : flux RSS/Atom via feedparser, en parallèle, avec cache."""

from __future__ import annotations

import html
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import feedparser

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.news.reader import web_url
from yumnews.catalog.http import ApiUnavailable, HttpClient
from yumnews.catalog.news.sources import CATEGORIES, SOURCES, SOURCES_BY_KEY, Source

log = logging.getLogger(__name__)
_TAG_RE = re.compile(r"<[^>]+>")
_IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.I)


class NewsClient:
    def __init__(
        self,
        http: HttpClient,
        cache: TtlCache,
        ttl: int = 900,
        workers: int = 8,
        reader=None,
    ) -> None:
        self.http = http
        self.cache = cache
        self.ttl = ttl
        self.workers = workers
        self.reader = reader  # [Sol] Liens de lecture persistants signés.

    @staticmethod
    def categories() -> list[dict]:
        return [{"key": k, "label": v} for k, v in CATEGORIES.items()]

    @staticmethod
    def sources(category: str | None = None) -> list[dict]:
        return [
            {
                "key": s.key,
                "name": s.name,
                "category": s.category,
                "country": s.country,
                "color": s.color,
                "site": s.site,
            }
            for s in SOURCES
            if category is None or s.category == category
        ]

    def feed(self, key: str, limit: int = 15) -> list[dict] | None:
        source = SOURCES_BY_KEY.get(key)
        if source is None:
            return None
        return self._articles(source)[:limit]

    def category(
        self, category: str, max_sources: int, per_source: int
    ) -> list[dict] | None:
        if category not in CATEGORIES:
            return None
        sources = [s for s in SOURCES if s.category == category][:max_sources]
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            batches = pool.map(lambda s: self._articles(s)[:per_source], sources)
        articles = [a for batch in batches for a in batch]
        articles.sort(key=lambda a: a["date"] or "", reverse=True)
        return articles

    def headlines(self, categories: list[str], per_category: int = 6) -> list[dict]:
        out = []
        for cat in categories:
            out.extend(
                (self.category(cat, max_sources=3, per_source=4) or [])[:per_category]
            )
        out.sort(key=lambda a: a["date"] or "", reverse=True)
        return out

    # ---- interne -------------------------------------------------------
    def _articles(self, source: Source) -> list[dict]:
        key = f"news:{source.key}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        try:
            text = self.http.get_text(
                source.url,
                headers={
                    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8"
                },
            )
        except ApiUnavailable as exc:
            log.warning("Flux %s indisponible : %s", source.key, exc)
            self.cache.set(key, [], ttl=300)  # évite de marteler une source en panne
            return []
        parsed = feedparser.parse(text)
        articles = [
            a for a in (self._article(e, source) for e in parsed.entries[:40]) if a
        ]
        self.cache.set(key, articles, ttl=self.ttl)
        return articles

    def _article(self, entry, source: Source) -> dict | None:
        link = entry.get("link")
        title = html.unescape(entry.get("title", "")).strip()
        if not web_url(link) or not title:
            return None
        summary_html = (
            entry.get("summary")
            or (entry.get("content") or [{}])[0].get("value", "")
            or ""
        )
        image = self._image(entry, summary_html)
        description = html.unescape(_TAG_RE.sub("", summary_html)).strip()
        description = re.sub(r"\s+", " ", description)[:320]
        article = {
            "id": entry.get("id") or link,
            "title": title,
            "link": link,
            "description": description,
            "image": image,
            "date": self._date(entry),
            "author": entry.get("author"),
            "source": {
                "key": source.key,
                "name": source.name,
                "color": source.color,
                "site": source.site,
                "country": source.country,
            },
            "category": source.category,
        }
        if self.reader:
            article["reader_url"] = self.reader.link(article, summary_html)
        return article

    @staticmethod
    def _image(entry, summary_html: str) -> str | None:
        for media in entry.get("media_content", []) or []:
            if media.get("url") and (
                media.get("medium") == "image"
                or str(media.get("type", "")).startswith("image")
                or not media.get("type")
            ):
                return media["url"]
        for thumb in entry.get("media_thumbnail", []) or []:
            if thumb.get("url"):
                return thumb["url"]
        for enc in entry.get("enclosures", []) or []:
            if str(enc.get("type", "")).startswith("image") and enc.get("href"):
                return enc["href"]
        for link in entry.get("links", []) or []:
            if str(link.get("type", "")).startswith("image") and link.get("href"):
                return link["href"]
        match = _IMG_RE.search(summary_html or "")
        return match.group(1) if match else None

    @staticmethod
    def _date(entry) -> str | None:
        for field in ("published_parsed", "updated_parsed"):
            value = entry.get(field)
            if value:
                try:
                    return datetime.fromtimestamp(
                        time.mktime(value), tz=timezone.utc
                    ).isoformat()
                except (OverflowError, ValueError):
                    continue
        return None
