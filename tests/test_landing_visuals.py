"""[Sol] Sélection France, disponibilité Netflix et fonctionnement sans source."""

from datetime import date, timedelta

from yumnews.catalog.cache import TtlCache
from yumnews.catalog.http import ApiUnavailable
from yumnews.catalog.tmdb.client import TmdbClient


class VisualHttp:
    def __init__(self, cinema_unavailable=False):
        self.calls = []
        self.cinema_unavailable = cinema_unavailable

    def get_json(self, url, params=None):
        self.calls.append((url, params))
        if url.endswith("/movie/now_playing"):
            if self.cinema_unavailable:
                raise ApiUnavailable("test")
            return {
                "results": [
                    {"id": 1, "title": "Film", "backdrop_path": "/film.jpg"},
                    {"id": 2, "title": "Sans image"},
                    {
                        "id": 3,
                        "title": "Adulte",
                        "backdrop_path": "/adult.jpg",
                        "adult": True,
                    },
                ]
            }
        return {"results": [{"id": 4, "name": "Série", "backdrop_path": "/tv.jpg"}]}


def test_visuals_alternate_and_use_french_netflix_recent_filter():
    http = VisualHttp()
    tmdb = TmdbClient("fake", http, TtlCache())
    visuals = tmdb.landing_visuals()
    assert [v["title"] for v in visuals] == ["Film", "Série"]
    assert visuals[0]["label"] == "En salles · France"
    assert visuals[1]["label"] == "Netflix · séries récentes"
    params = next(params for url, params in http.calls if url.endswith("/discover/tv"))
    assert params["watch_region"] == "FR" and params["with_watch_providers"] == "8"
    assert params["with_watch_monetization_types"] == "flatrate"
    assert (
        params["first_air_date.gte"] == (date.today() - timedelta(days=120)).isoformat()
    )
    assert params["first_air_date.lte"] == date.today().isoformat()
    assert "api_key" not in str(visuals)
    tmdb.landing_visuals()
    assert len(http.calls) == 2


def test_one_source_outage_keeps_other_visuals():
    tmdb = TmdbClient("fake", VisualHttp(cinema_unavailable=True), TtlCache())
    assert [v["title"] for v in tmdb.landing_visuals()] == ["Série"]


def test_public_landing_works_without_api_credentials(client, container):
    container.tmdb.api_key = ""
    assert client.get("/api/landing/visuals").json == {"ok": True, "results": []}
    page = client.get("/")
    assert page.status_code == 200
    for text in (
        "Tout ce qui sort",
        "landingTrending",
        "features",
        "landingStoryTitle",
        "landingEditorialTitle",
    ):
        assert text.encode() in page.data
