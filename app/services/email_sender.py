"""
Envío de email con adjunto PDF vía SMTP (Gmail).

Requisitos Gmail:
- Usar App Password (no contraseña normal)
- SMTP: smtp.gmail.com:587 con STARTTLS
"""

from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailSendError(RuntimeError):
    pass


def send_email_with_attachment(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    attachment_filename: str,
    attachment_bytes: bytes,
) -> None:
    if not settings.smtp_host or not settings.smtp_port:
        raise EmailSendError("SMTP_HOST/SMTP_PORT no configurados")
    if not settings.smtp_user or not settings.smtp_password:
        raise EmailSendError("SMTP_USER/SMTP_PASSWORD no configurados")
    if not settings.mail_from:
        raise EmailSendError("MAIL_FROM no configurado")

    msg = EmailMessage()
    msg["From"] = settings.mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body_text)

    mime_type, _ = mimetypes.guess_type(attachment_filename)
    if not mime_type:
        mime_type = "application/octet-stream"
    maintype, subtype = mime_type.split("/", 1)

    msg.add_attachment(
        attachment_bytes,
        maintype=maintype,
        subtype=subtype,
        filename=attachment_filename,
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except Exception as e:
        raise EmailSendError(f"Fallo enviando email SMTP: {e}")

