from __future__ import annotations

from typing import Any

from .catalog import nombre_cliente
from .console_view import imprimir_resumen
from .config_validation import validar_config
from .data_access import cargar_datos_cliente_periodo, descubrir_todos_los_rfcs_con_periodo
from .emailing import enviar_email, resolve_email_destinatarios
from .logging_utils import setup_logging
from .rendering import hash_alertas, render_html_cliente, render_html_ejecutivo
from .rules import evaluar_cliente_periodo, evaluar_todos
from .settings import MESES_ES
from .storage import HistorialAlertasRepository


logger = setup_logging()


def cargar_config_validada(cfg: dict[str, Any]) -> dict[str, Any]:
    return validar_config(cfg).raw


def ejecutar_modo_director(
    periodo: str,
    cfg: dict[str, Any],
    clientes: dict[str, Any],
    piloto: bool,
    forzar: bool,
    historial: HistorialAlertasRepository,
) -> None:
    logger.info("Modo DIRECTOR - periodo %s", periodo)

    alertas = evaluar_todos(
        periodo,
        cfg,
        clientes,
        logger,
        descubrir_todos_los_rfcs_con_periodo,
        cargar_datos_cliente_periodo,
    )
    if not alertas:
        logger.info("Sin alertas para este periodo.")
        return

    imprimir_resumen(alertas, clientes)

    if piloto:
        logger.info("Modo piloto - correo no enviado.")
        return

    hash_contenido = hash_alertas(alertas)
    destinatarios = resolve_email_destinatarios(cfg["notificaciones"]["email"].get("destinatarios", []))
    if not forzar and historial.ya_enviado("DIRECTOR", periodo, "director", hash_contenido):
        logger.info("Ya se envio este reporte exacto para este periodo. Usa --forzar para reenviar.")
        return

    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    altas = sum(1 for alerta in alertas if alerta.severidad == "ALTA")
    asunto = f"[CONTSIS] {'Prioridad alta: ' + str(altas) if altas else 'Reporte'} - {mes_label} {year}"
    html = render_html_ejecutivo(alertas, periodo, clientes)

    if enviar_email(destinatarios, asunto, html, cfg, logger):
        historial.registrar_envio("DIRECTOR", periodo, "director", hash_contenido, destinatarios)
        return
    raise RuntimeError(f"No se pudo enviar el correo de alertas del director para {periodo}.")


def ejecutar_modo_cliente(
    rfc: str,
    periodo: str,
    cfg: dict[str, Any],
    clientes: dict[str, Any],
    piloto: bool,
    forzar: bool,
    historial: HistorialAlertasRepository,
) -> None:
    logger.info("Modo CLIENTE - RFC %s periodo %s", rfc, periodo)

    nombre = nombre_cliente(rfc, clientes)
    datos = cargar_datos_cliente_periodo(rfc, periodo, logger)
    if not datos.tiene_e and not datos.tiene_r:
        logger.error("No se encontraron Excel para %s en %s", rfc, periodo)
        raise FileNotFoundError(f"No se encontraron Excel para {rfc} en {periodo}.")

    alertas_cliente = evaluar_cliente_periodo(datos, cfg, clientes, logger)
    logger.info("%s: %s alerta(s)", nombre, len(alertas_cliente))

    if piloto:
        imprimir_resumen(alertas_cliente, clientes)
        logger.info("Modo piloto - correo no enviado.")
        return

    hash_contenido = hash_alertas(alertas_cliente)
    if not forzar and historial.ya_enviado(rfc, periodo, "cliente", hash_contenido):
        logger.info("Ya se envio reporte a %s para %s. Usa --forzar para reenviar.", nombre, periodo)
        return

    destinatarios = resolve_email_destinatarios(cfg["notificaciones"]["email"].get("destinatarios", []))
    if not destinatarios:
        logger.warning("No hay destinatarios de director configurados para pruebas de envio a %s", nombre)
        raise RuntimeError(f"No hay destinatarios configurados para el envio de alertas de {nombre}.")

    logger.info("Prueba de correo cliente redirigida a destinatarios de director: %s", ", ".join(destinatarios))

    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    asunto = f"Reporte Mensual CFDI - {nombre} - {mes_label} {year}"
    html = render_html_cliente(rfc, periodo, alertas_cliente, datos, clientes, logo_mode="cid")

    if enviar_email(destinatarios, asunto, html, cfg, logger):
        historial.registrar_envio(rfc, periodo, "cliente", hash_contenido, destinatarios)
        return
    raise RuntimeError(f"No se pudo enviar el correo de alertas de {nombre} para {periodo}.")
