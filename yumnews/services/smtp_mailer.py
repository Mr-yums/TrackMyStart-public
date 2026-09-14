"""[Sol] Courrier transactionnel SMTP TLS, catégorie stable et adresse de réponse."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from yumnews.services.mailer import Mailer

log = logging.getLogger(__name__)
CHANNELS = {
    "acces": ("ACCES", "acces@trackmystart.de"),
    "support": ("SUPPORT", "support@trackmystart.de"),
}


class SMTPMailer(Mailer):
    def __init__(self, host, port, username, password, sender, timeout=15):
        if port not in (465, 587) or not all((host, username, password, sender)):
            raise ValueError("Configuration SMTP TLS incomplète")
        self.host, self.port, self.username = host, port, username
        self.password, self.sender, self.timeout = password, sender, timeout

    def send(self, email):
        category, reply_to = CHANNELS.get(email.category, CHANNELS["support"])
        try:
            msg = EmailMessage()
            msg["From"] = f"TrackMyStart <{self.sender}>"
            msg["To"] = email.to
            msg["Reply-To"] = reply_to
            msg["Subject"] = f"[TMS:{category}] {email.subject}"
            msg["X-TrackMyStart-Category"] = category
            msg["Message-ID"] = make_msgid(domain="trackmystart.de")
            msg["Date"] = formatdate(localtime=False)
            msg["Auto-Submitted"] = "auto-generated"
            msg.set_content(
                email.text
                + "\n\nBesoin d’aide ? Répondez à ce message. Ne communiquez jamais votre mot de passe.\n"
            )
            if email.html:
                msg.add_alternative(email.html, subtype="html")
            context = ssl.create_default_context()
            if self.port == 465:
                connection = smtplib.SMTP_SSL(
                    self.host, self.port, timeout=self.timeout, context=context
                )
            else:
                connection = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with connection as smtp:
                smtp.ehlo()
                if self.port == 587:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                smtp.login(self.username, self.password)
                rejected = smtp.send_message(msg)
                if rejected:
                    log.error("SMTP : destinataire refusé (%s)", category)
                    return False
            return True
        except (OSError, smtplib.SMTPException, ValueError) as exc:
            # [Sol] Pas de liens de réinitialisation, destinataires ou secrets dans les logs.
            # Pas de renvoi automatique : une déconnexion peut suivre une acceptation.
            log.error(
                "SMTP : envoi non confirmé (%s, %s)", category, type(exc).__name__
            )
            return False
