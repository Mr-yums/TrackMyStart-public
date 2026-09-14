"""[Sol] Lecture interne, instantané signé, source facultative et accès inchangés."""

from unittest.mock import Mock
import pytest
from yumnews.catalog.news.reader import PressReader, excerpt
from yumnews.catalog.news.sources import SOURCES_BY_KEY
from yumnews.editorial.stories import STORIES


def article(
    container,
    source="premiere",
    markup="<p>Une annonce de casting présentée par la rédaction.</p>",
):
    return container.news._article(
        {
            "title": "Netflix prépare un nouveau film",
            "link": "https://www.premiere.fr/test",
            "summary": markup,
        },
        SOURCES_BY_KEY[source],
    )


def test_reader_survives_cache_clear_and_uses_same_visual_language(client, container):
    item = article(container)
    assert item["reader_url"].startswith("/lecture/")
    container.cache.clear()
    container.http.get_text = Mock(
        side_effect=AssertionError("Aucun accès réseau pendant la lecture")
    )
    response = client.get(item["reader_url"])
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert (
        "theme-netflix" in html
        and "editorial-polish.css" in html
        and "editorial-polish.js" in html
    )
    assert "Une annonce de casting" in html and "Extrait transmis par la source" in html
    assert (
        "https://www.premiere.fr/test" in html
        and "Consulter la source originale" in html
    )
    token = item["reader_url"].split("/lecture/")[1]
    assert (
        PressReader(container.settings.secret_key)
        .read(token)["text"]
        .startswith("Une annonce")
    )


def test_reader_does_not_bypass_premium(client, container):
    assert client.get(article(container, source="ann")["reader_url"]).status_code == 402


def test_bad_signature_and_unknown_source_are_rejected(client, container):
    item = article(container)
    assert client.get(item["reader_url"] + "x").status_code == 404
    token = container.press_reader.signer.dumps(
        {"source": "unknown", "url": "https://example.com"}
    )
    assert client.get("/lecture/" + token).status_code == 404


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,test",
        "https://user:password@example.com/x",
    ],
)
def test_unsafe_source_links_rejected(container, url):
    assert (
        container.news._article(
            {"title": "Test", "link": url}, SOURCES_BY_KEY["premiere"]
        )
        is None
    )


def test_source_html_not_executed_and_excerpt_is_bounded(client, container):
    item = article(
        container,
        markup="<script>secret()</script><p>Bonjour &amp; bienvenue.</p>"
        + ("mot " * 300),
    )
    page = client.get(item["reader_url"]).get_data(as_text=True)
    assert "secret()" not in page
    assert "Bonjour &amp; bienvenue." in page
    assert len(excerpt("mot " * 300).split()) == 180


def test_no_excerpt_is_explained_not_invented(client, container):
    html = client.get(article(container, markup="")["reader_url"]).get_data(
        as_text=True
    )
    assert "aucun extrait" in html


def test_existing_original_brief_has_priority(container):
    item = container.news._article(
        {"title": "Netflix", "link": STORIES[0]["source_url"], "summary": "Texte flux"},
        SOURCES_BY_KEY["premiere"],
    )
    assert item["reader_url"] == "/actualites/" + STORIES[0]["slug"]
