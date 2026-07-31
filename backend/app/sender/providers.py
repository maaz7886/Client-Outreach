"""Sending adapters behind one protocol. SMTP is the v1 implementation
(works with Brevo, Zoho, Gmail app-password, any relay). Gmail API and
Microsoft Graph adapters plug in here later without touching the service."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

from app.core.config import get_settings


@dataclass
class OutgoingEmail:
    to: str
    subject: str
    body_text: str
    from_name: str
    from_email: str


class SendResult:
    def __init__(self, ok: bool, provider_message_id: str | None = None, error: str | None = None):
        self.ok = ok
        self.provider_message_id = provider_message_id
        self.error = error


class EmailSenderProvider(Protocol):
    name: str

    def send(self, email: OutgoingEmail) -> SendResult: ...


class SMTPSender:
    name = "smtp"

    def __init__(self, host: str | None = None, port: int | None = None,
                 username: str | None = None, password: str | None = None):
        s = get_settings()
        self.host = host or s.smtp_host
        self.port = port or s.smtp_port
        self.username = username if username is not None else s.smtp_username
        self.password = password if password is not None else s.smtp_password
        if not self.host:
            raise ValueError("SMTP_HOST not configured")

    def send(self, email: OutgoingEmail) -> SendResult:
        msg = MimeMessage()
        msg["From"] = f"{email.from_name} <{email.from_email}>"
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.body_text)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
                smtp.starttls()
                if self.username:
                    smtp.login(self.username, self.password)
                smtp.send_message(msg)
            return SendResult(ok=True, provider_message_id=msg["Message-Id"])
        except smtplib.SMTPRecipientsRefused as exc:
            return SendResult(ok=False, error=f"recipient refused: {exc.recipients}")
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(ok=False, error=str(exc))
