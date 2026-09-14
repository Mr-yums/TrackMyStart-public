"""Envoi d'emails : SendGrid via HTTP si une clé est configurée, sinon journalisation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None
    category: str = "support"  # [Sol] Routage des réponses de support.


class Mailer(ABC):
    @abstractmethod
    def send(self, email: Email) -> bool: ...


class LoggingMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> bool:
        self.sent.append(email)
        log.info(
            "[Sol] Courriel simulé : aucun envoi externe (contenu privé non journalisé)."
        )
        return True


class SendGridMailer(Mailer):
    ENDPOINT = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self, api_key: str, sender: str, timeout: int = 10) -> None:
        self.api_key = api_key
        self.sender = sender
        self.timeout = timeout

    def send(self, email: Email) -> bool:
        content = [{"type": "text/plain", "value": email.text}]
        if email.html:
            content.append({"type": "text/html", "value": email.html})
        payload = {
            "personalizations": [{"to": [{"email": email.to}]}],
            "from": {"email": self.sender},
            "subject": email.subject,
            "content": content,
        }
        try:
            response = requests.post(
                self.ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            if response.status_code >= 300:
                log.error("SendGrid %s : %s", response.status_code, response.text[:300])
                return False
            return True
        except requests.RequestException as exc:
            log.error("SendGrid injoignable : %s", exc)
            return False
