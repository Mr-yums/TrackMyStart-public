"""Cache mémoire à TTL, thread-safe, avec purge paresseuse (pas de croissance infinie)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Callable


class TtlCache:
    def __init__(self, default_ttl: int = 3600, max_entries: int = 2000) -> None:
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(namespace: str, params: Any = None) -> str:
        digest = hashlib.md5(
            json.dumps(params, sort_keys=True, default=str).encode(),
            usedforsecurity=False,
        ).hexdigest()
        return f"{namespace}:{digest}"

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            expires, value = entry
            if expires < time.time():
                del self._store[key]
                self.misses += 1
                return None
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        with self._lock:
            if len(self._store) >= self.max_entries:
                self._purge_locked()
            self._store[key] = (time.time() + (ttl or self.default_ttl), value)

    def get_or_set(
        self, key: str, loader: Callable[[], Any], ttl: int | None = None
    ) -> Any:
        value = self.get(key)
        if value is None:
            value = loader()
            if value is not None:
                self.set(key, value, ttl)
        return value

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
            }

    def _purge_locked(self) -> None:
        now = time.time()
        for k in [k for k, (exp, _) in self._store.items() if exp < now]:
            del self._store[k]
        if (
            len(self._store) >= self.max_entries
        ):  # toujours plein : on retire les plus anciens
            for k in sorted(self._store, key=lambda k: self._store[k][0])[
                : self.max_entries // 4
            ]:
                del self._store[k]
