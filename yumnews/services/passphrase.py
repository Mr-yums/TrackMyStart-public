"""Génération du seed premium : jeton opaque copiable-collable, façon clé BTC.

Chaîne alphanumérique minuscule (``[a-z0-9]``), sans caractère ambigu de séparation,
à très forte entropie : le client la copie-colle telle quelle dans le bot Discord.
40 caractères sur 36 symboles ≈ 206 bits — unique en pratique, impossible à deviner.
"""

from __future__ import annotations

import secrets

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def generate_seed(length: int = 40) -> str:
    """Renvoie p.ex. ``eori719891687723698ezf8e19f7zef3k2a9x1c7p`` (minuscules + chiffres)."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
