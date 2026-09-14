"""[Sol] TLS obligatoire, canal de réponse, aucun secret journalisé et aide publique."""

from dataclasses import replace
from unittest.mock import MagicMock, patch
import smtplib
from yumnews.services.smtp_mailer import SMTPMailer
from yumnews.services.mailer import Email
from yumnews.container import Container


def test_smtp_tls_reply_and_category():
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    with patch("yumnews.services.smtp_mailer.smtplib.SMTP", return_value=smtp):
        assert SMTPMailer(
            "smtp.example", 587, "login", "key", "contact@trackmystart.de"
        ).send(Email("client@example.org", "Votre lien", "Texte", category="acces"))
    assert [x[0] for x in smtp.method_calls] == [
        "ehlo",
        "starttls",
        "ehlo",
        "login",
        "send_message",
    ]
    msg = smtp.send_message.call_args.args[0]
    assert msg["Reply-To"] == "acces@trackmystart.de"
    assert msg["Subject"].startswith("[TMS:ACCES]")
    assert msg["To"] == "client@example.org"
    assert "key" not in msg.as_string()


def test_smtp_failure_is_not_retried_or_logged_with_token(caplog):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.side_effect = smtplib.SMTPServerDisconnected(
        "secret-token-do-not-log"
    )
    with patch("yumnews.services.smtp_mailer.smtplib.SMTP", return_value=smtp):
        assert not SMTPMailer(
            "smtp.example", 587, "login", "key", "contact@trackmystart.de"
        ).send(Email("client@example.org", "Reset", "secret-token-do-not-log"))
    assert smtp.send_message.call_count == 1
    assert "secret-token-do-not-log" not in caplog.text
    assert "client@example.org" not in caplog.text


def test_container_selects_smtp(settings):
    c = Container(
        replace(
            settings,
            smtp_host="smtp.example",
            smtp_username="login",
            smtp_password="key",
        )
    )
    assert isinstance(c.mailer, SMTPMailer)
    c.db.remove()


def test_support_without_login_or_ads(client):
    response = client.get("/aide")
    assert response.status_code == 200
    for name in ("support", "acces", "incidents", "suppression"):
        assert f"mailto:{name}@trackmystart.de" in response.text
    assert "/mot-de-passe-oublie" in response.text
    assert "adsbygoogle.js" not in response.text
    assert "/aide" in client.get("/").text
