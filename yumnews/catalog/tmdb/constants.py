"""Constantes TMDB : genres, plateformes officielles (pour « Où regarder »)."""

from __future__ import annotations

from dataclasses import dataclass

MOVIE_GENRES: dict[str, tuple[int, str]] = {
    "action": (28, "Action"),
    "aventure": (12, "Aventure"),
    "animation": (16, "Animation"),
    "comedie": (35, "Comédie"),
    "crime": (80, "Crime"),
    "documentaire": (99, "Documentaire"),
    "drame": (18, "Drame"),
    "famille": (10751, "Famille"),
    "fantastique": (14, "Fantastique"),
    "histoire": (36, "Histoire"),
    "horreur": (27, "Horreur"),
    "musique": (10402, "Musique"),
    "mystere": (9648, "Mystère"),
    "romance": (10749, "Romance"),
    "sf": (878, "Science-fiction"),
    "thriller": (53, "Thriller"),
    "guerre": (10752, "Guerre"),
    "western": (37, "Western"),
}

TV_GENRES: dict[str, tuple[int, str]] = {
    "action": (10759, "Action & Aventure"),
    "animation": (16, "Animation"),
    "comedie": (35, "Comédie"),
    "crime": (80, "Crime"),
    "documentaire": (99, "Documentaire"),
    "drame": (18, "Drame"),
    "famille": (10751, "Famille"),
    "enfants": (10762, "Enfants"),
    "mystere": (9648, "Mystère"),
    "reality": (10764, "Télé-réalité"),
    "sf": (10765, "SF & Fantastique"),
    "soap": (10766, "Soap"),
    "guerre": (10768, "Guerre & Politique"),
    "western": (37, "Western"),
}

ORIGIN_COUNTRIES = "US|FR|GB|CA|AU|IE|NZ|BE|CH|JP|KR|ES|IT|DE"


@dataclass(frozen=True)
class Platform:
    key: str
    name: str
    color: str
    home_url: str
    search_url: str  # {q} sera remplacé par le titre encodé
    tmdb_provider_ids: tuple[int, ...] = ()
    tmdb_network_ids: tuple[int, ...] = ()

    def search_link(self, title: str) -> str:
        from urllib.parse import quote_plus

        return self.search_url.format(q=quote_plus(title))


PLATFORMS: dict[str, Platform] = {
    p.key: p
    for p in (
        Platform(
            "netflix",
            "Netflix",
            "#E50914",
            "https://www.netflix.com/fr/",
            "https://www.netflix.com/search?q={q}",
            (8,),
            (213,),
        ),
        Platform(
            "prime",
            "Prime Video",
            "#00A8E1",
            "https://www.primevideo.com/",
            "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={q}",
            (119, 9, 10, 2100),
            (1024,),
        ),
        Platform(
            "disney",
            "Disney+",
            "#113CCF",
            "https://www.disneyplus.com/fr-fr",
            "https://www.disneyplus.com/fr-fr/search?q={q}",
            (337,),
            (2739,),
        ),
        Platform(
            "apple",
            "Apple TV+",
            "#8E8E93",
            "https://tv.apple.com/fr",
            "https://tv.apple.com/fr/search?term={q}",
            (350, 2),
            (2552,),
        ),
        Platform(
            "max",
            "Max",
            "#002BE7",
            "https://www.max.com/fr/fr",
            "https://www.max.com/fr/fr/search?q={q}",
            (1899, 384),
            (49, 3186),
        ),
        Platform(
            "canal",
            "Canal+",
            "#111111",
            "https://www.canalplus.com/",
            "https://www.canalplus.com/recherche/?q={q}",
            (381, 345),
            (285,),
        ),
        Platform(
            "paramount",
            "Paramount+",
            "#0064FF",
            "https://www.paramountplus.com/fr/",
            "https://www.paramountplus.com/fr/search/?q={q}",
            (531, 582),
            (4330,),
        ),
        Platform(
            "crunchyroll",
            "Crunchyroll",
            "#F47521",
            "https://www.crunchyroll.com/fr",
            "https://www.crunchyroll.com/fr/search?q={q}",
            (283,),
        ),
        Platform(
            "adn",
            "ADN",
            "#0096D6",
            "https://animationdigitalnetwork.com/",
            "https://animationdigitalnetwork.com/recherche?q={q}",
            (415,),
        ),
        Platform(
            "ocs",
            "OCS",
            "#FF6A00",
            "https://www.ocs.fr/",
            "https://www.ocs.fr/recherche?q={q}",
            (56,),
        ),
        Platform(
            "arte",
            "Arte",
            "#FA4B0A",
            "https://www.arte.tv/fr/",
            "https://www.arte.tv/fr/search/?q={q}",
            (234,),
            (62,),
        ),
        Platform(
            "francetv",
            "France.tv",
            "#0A0A2A",
            "https://www.france.tv/",
            "https://www.france.tv/recherche/?q={q}",
            (236,),
        ),
        Platform(
            "tf1",
            "TF1+",
            "#1B48D2",
            "https://www.tf1.fr/",
            "https://www.tf1.fr/recherche?q={q}",
            (1754,),
        ),
        Platform(
            "youtube",
            "YouTube",
            "#FF0000",
            "https://www.youtube.com/",
            "https://www.youtube.com/results?search_query={q}",
            (192,),
        ),
        Platform(
            "cinema",
            "Au cinéma",
            "#f5c518",
            "https://www.allocine.fr/",
            "https://www.allocine.fr/rechercher/?q={q}",
        ),
    )
}

PROVIDER_TO_PLATFORM: dict[int, Platform] = {
    pid: p for p in PLATFORMS.values() for pid in p.tmdb_provider_ids
}
NETWORK_TO_PLATFORM: dict[int, Platform] = {
    nid: p for p in PLATFORMS.values() for nid in p.tmdb_network_ids
}

# Ordre d'affichage des filtres plateformes dans l'onglet Séries
SERIES_PROVIDER_KEYS = (
    "netflix",
    "prime",
    "disney",
    "apple",
    "max",
    "canal",
    "paramount",
    "crunchyroll",
    "arte",
)
