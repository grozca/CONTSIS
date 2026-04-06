from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


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
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = f"CONTSIS <{remitente}>"
        msg["To"] = ", ".join(destinatarios)
        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

        with smtplib.SMTP(ecfg["smtp_server"], ecfg["smtp_port"]) as server:
            server.starttls()
            server.login(remitente, password)
            server.sendmail(remitente, destinatarios, msg.as_string())

        logger.info("Correo enviado a: %s", ", ".join(destinatarios))
        return True
    except Exception as exc:
        logger.error("Error enviando correo: %s", exc)
        return False

