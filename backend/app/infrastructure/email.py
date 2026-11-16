"""SMTP adapter for the `EmailSender` port. Provider-neutral (ADR-0003)."""

from email.message import EmailMessage as MimeMessage

import aiosmtplib

from app.application.ports import EmailMessage
from app.config import Settings


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._settings.smtp_from
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body)

        password = self._settings.smtp_password
        await aiosmtplib.send(
            mime,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=self._settings.smtp_username,
            password=password.get_secret_value() if password else None,
            start_tls=self._settings.smtp_starttls,
            use_tls=self._settings.smtp_use_tls,
            timeout=self._settings.smtp_timeout_seconds,
        )
