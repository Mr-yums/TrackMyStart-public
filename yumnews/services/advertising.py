"""[Sol] Campagne directe facultative, publication atomique et aucune régie implicite."""

from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from yumnews.services.errors import ValidationError

DEFAULT = {"enabled": False, "interstitial": False, "campaign": {}}
PLACEMENTS = {"home", "catalog", "reader", "actor_break"}


class Advertising:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = ""
        try:
            data = self.validate(json.loads(raw)) if raw else deepcopy(DEFAULT)
        except (ValueError, ValidationError):
            data = deepcopy(DEFAULT)
        return data, hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def validate(data):
        if (
            not isinstance(data, dict)
            or set(data) != {"enabled", "interstitial", "campaign"}
            or any(type(data[k]) is not bool for k in ("enabled", "interstitial"))
        ):
            raise ValidationError("Configuration publicitaire invalide.")
        c = data["campaign"]
        if not isinstance(c, dict):
            raise ValidationError("Campagne invalide.")
        fields = {
            "title",
            "description",
            "sponsor",
            "image_url",
            "target_url",
            "starts_at",
            "ends_at",
            "placements",
        }
        if not c and not data["enabled"]:
            return deepcopy(data)
        if set(c) != fields:
            raise ValidationError("Campagne incomplète.")
        for field, maximum in [
            ("title", 150),
            ("description", 300),
            ("sponsor", 100),
            ("image_url", 2000),
            ("target_url", 2000),
            ("starts_at", 40),
            ("ends_at", 40),
        ]:
            if (
                not isinstance(c[field], str)
                or not c[field].strip()
                or len(c[field]) > maximum
            ):
                raise ValidationError("Champ de campagne invalide : " + field)
        for field in ("image_url", "target_url"):
            try:
                url = urlsplit(c[field])
                valid = (
                    url.scheme == "https"
                    and url.hostname
                    and not url.username
                    and not url.password
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValidationError(
                    "Les liens publicitaires doivent utiliser HTTPS sans identifiant."
                )
        try:
            start = datetime.fromisoformat(c["starts_at"])
            end = datetime.fromisoformat(c["ends_at"])
            if start.tzinfo is None or end.tzinfo is None or start >= end:
                raise ValueError()
        except ValueError:
            raise ValidationError(
                "Dates invalides : indiquez un début et une fin avec fuseau horaire."
            ) from None
        if (
            not isinstance(c["placements"], list)
            or not c["placements"]
            or any(
                not isinstance(p, str) or p not in PLACEMENTS for p in c["placements"]
            )
        ):
            raise ValidationError("Emplacements invalides.")
        return deepcopy(data)

    def save(self, data, revision):
        data = self.validate(data)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(str(self.path) + ".lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.read()[1] != revision:
                raise ValidationError(
                    "La campagne a été modifiée ailleurs. Rechargez avant de réessayer."
                )
            name = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=self.path.parent, delete=False
                ) as output:
                    name = output.name
                    json.dump(data, output, ensure_ascii=False)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(name, self.path)
            finally:
                if name and os.path.exists(name):
                    os.unlink(name)
        return self.read()

    def placement(self, policy, placement, now=None):
        # Sortie avant toute lecture de campagne pour un membre Premium.
        if policy.can("ad_free") or placement not in PLACEMENTS:
            return None
        try:
            data = self.validate(self.read()[0])
        except (OSError, ValueError, ValidationError):
            return None
        if not data["enabled"] or (
            placement == "actor_break" and not data["interstitial"]
        ):
            return None
        c = data["campaign"]
        now = now or datetime.now(timezone.utc)
        if placement not in c["placements"] or not datetime.fromisoformat(
            c["starts_at"]
        ) <= now < datetime.fromisoformat(c["ends_at"]):
            return None
        return {
            key: c[key]
            for key in ("title", "description", "sponsor", "image_url", "target_url")
        }
