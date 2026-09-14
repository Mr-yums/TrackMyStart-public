"""Client HTTP minimal partagé par les adaptateurs d'API (timeouts, UA, erreurs)."""

from __future__ import annotations

import logging
from typing import Any

import requests

log = logging.getLogger(__name__)


class ApiUnavailable(Exception):
    pass


class HttpClient:
    def __init__(
        self, user_agent: str = "TrackMyStart/1.0 (+news site)", timeout: int = 10
    ) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )

    def get_json(
        self, url: str, params: dict | None = None, headers: dict | None = None
    ) -> Any:
        try:
            response = self._session.get(
                url, params=params, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            log.warning("GET %s : %s", url, exc)
            raise ApiUnavailable(str(exc)) from exc
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            log.warning(
                "GET %s → %s %s", url, response.status_code, response.text[:120]
            )
            raise ApiUnavailable(f"HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise ApiUnavailable("JSON invalide") from exc

    def post_json(self, url: str, payload: dict, headers: dict | None = None) -> Any:
        try:
            response = self._session.post(
                url, json=payload, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise ApiUnavailable(str(exc)) from exc
        if response.status_code >= 400:
            raise ApiUnavailable(f"HTTP {response.status_code}")
        return response.json()

    def get_bytes(self, url: str, headers: dict | None = None) -> tuple[bytes, str]:
        try:
            response = self._session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiUnavailable(str(exc)) from exc
        return response.content, response.headers.get(
            "Content-Type", "application/octet-stream"
        )

    def get_text(self, url: str, headers: dict | None = None) -> str:
        try:
            response = self._session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ApiUnavailable(str(exc)) from exc
        return response.text
