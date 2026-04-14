"""SMTP smoke test using the shared email service."""

import os

from alertas.app.emailing import resolve_email_destinatarios
from alertas.app.logging_utils import setup_logging
from alertas.app.settings import cargar_config


def main() -> None:
    logger = setup_logging()
    cfg = cargar_config()
    destinatarios = resolve_email_destinatarios(cfg["notificaciones"]["email"].get("destinatarios", []))

    logger.info("EMAIL_REMITENTE cargado: %s", "si" if os.getenv("EMAIL_REMITENTE") else "no")
    logger.info("EMAIL_PASSWORD cargado: %s", "si" if os.getenv("EMAIL_PASSWORD") else "no")
    logger.info("Destinatarios resueltos: %s", ", ".join(destinatarios) if destinatarios else "ninguno")
    logger.info("Prueba manual pendiente: usar app.emailing.enviar_email(...) con un HTML de prueba controlado.")


if __name__ == "__main__":
    main()
