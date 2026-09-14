"""Tests du catalogue avec un HttpClient factice (aucun appel réseau)."""

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.tmdb import normalizer
from yumnews.catalog.tmdb.client import TmdbClient
from yumnews.payments.nowpayments_gateway import NowPaymentsGateway
from config import NowPaymentsSettings


class FakeHttp:
    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls = 0

    def get_json(self, url, params=None, headers=None):
        self.calls += 1
        for key, value in self.routes.items():
            if url.endswith(key):
                return value
        return None


def test_tmdb_client_caches_and_normalizes():
    raw = {
        "results": [
            {
                "id": 1,
                "title": "Dune",
                "release_date": "2024-03-01",
                "poster_path": "/p.jpg",
                "vote_average": 8.25,
                "original_language": "en",
                "genre_ids": [878],
            },
            {
                "id": 2,
                "title": "Sans affiche",
                "release_date": "2024-01-01",
                "poster_path": None,
                "vote_average": 5,
                "original_language": "en",
            },
        ]
    }
    http = FakeHttp({"/trending/movie/week": raw})
    client = TmdbClient("key", http, TtlCache())
    items = client.trending_movies()
    assert [i["id"] for i in items] == [1]
    assert (
        items[0]["poster"] == "https://image.tmdb.org/t/p/w500/p.jpg"
        and items[0]["year"] == "2024"
        and items[0]["rating"] == 8.2
    )
    client.trending_movies()
    assert http.calls == 1  # 2e appel servi par le cache


def test_watch_offers_map_official_platforms():
    providers = {
        "results": {
            "FR": {
                "link": "https://justwatch/x",
                "flatrate": [
                    {
                        "provider_id": 8,
                        "provider_name": "Netflix",
                        "logo_path": "/n.png",
                    }
                ],
                "rent": [
                    {"provider_id": 9999, "provider_name": "Inconnu", "logo_path": None}
                ],
            }
        }
    }
    watch = normalizer.watch_offers(providers, "FR", "Dune")
    assert (
        watch["offers"][0]["official"]
        and "netflix.com/search?q=Dune" in watch["offers"][0]["url"]
    )
    assert (
        watch["offers"][1]["official"] is False
        and watch["offers"][1]["url"] == "https://justwatch/x"
    )


def test_nowpayments_signature_roundtrip():
    gw = NowPaymentsGateway(NowPaymentsSettings(api_key="k", ipn_secret="secret"))
    payload = {
        "order_id": "abc",
        "payment_status": "finished",
        "payment_id": 42,
        "price_amount": 12,
    }
    import json

    body = json.dumps(payload).encode()
    note = gw.parse_notification(body, gw.sign(payload))
    assert note.succeeded and note.final and note.order_id == "abc"
    import pytest

    from yumnews.services.errors import PaymentError

    with pytest.raises(PaymentError):
        gw.parse_notification(body, "deadbeef")
