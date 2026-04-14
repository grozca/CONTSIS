from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from typing import Any

from .rendering import LOGO_CID, LOGO_PATH


def resolve_email_destinatarios(defaults: list[str] | None = None) -> list[str]:
    destinatarios_env = os.getenv("EMAIL_DESTINATARIOS", "")
    if destinatarios_env.strip():
        return [item.strip() for item in destinatarios_env.split(",") if item.strip()]
    return defaults or []


def enviar_email(
    destinatarios: list[str],
    asunto: str,
    cuerpo_html: str,
    cfg: dict[str, Any],
    logger: logging.Logger,
) -> bool:
    ecfg = cfg["notificaciones"]["email"]
    remitente = os.getenv("EMAIL_REMITENTE", "")
    password = os.getenv("EMAIL_PASSWORD", "")

    if not all([remitente, password, destinatarios]):
        logger.warning("Email no configurado: faltan credenciales o destinatarios en .env")
        return False

    try:
        msg = MIMEMultipart("related")
        msg["Subject"] = asunto
        msg["From"] = f"CONTSIS <{remitente}>"
        msg["To"] = ", ".join(destinatarios)
        alternative = MIMEMultipart("alternative")
        alternative.attach(MIMEText(cuerpo_html, "html", "utf-8"))
        msg.attach(alternative)

        if f"cid:{LOGO_CID}" in cuerpo_html and LOGO_PATH.exists():
            logo_part = MIMEImage(LOGO_PATH.read_bytes(), _subtype="png")
            logo_part.add_header("Content-ID", f"<{LOGO_CID}>")
            logo_part.add_header("Content-Disposition", "inline", filename=LOGO_PATH.name)
            msg.attach(logo_part)

        with smtplib.SMTP(ecfg["smtp_server"], ecfg["smtp_port"]) as server:
            server.starttls()
            server.login(remitente, password)
            server.sendmail(remitente, destinatarios, msg.as_string())

        logger.info("Correo enviado a: %s", ", ".join(destinatarios))
        return True
    except Exception as exc:
        logger.error("Error enviando correo: %s", exc)
        return False

