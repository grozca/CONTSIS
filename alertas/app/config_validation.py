from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


class ConfigValidationError(ValueError):
    """Raised when the alert engine configuration is invalid."""


@dataclass(frozen=True, slots=True)
class ValidatedConfig:
    raw: dict[str, Any]


def _require_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ConfigValidationError(f"La seccion '{key}' es obligatoria y debe ser un objeto.")
    return value


def _require_bool(section: dict[str, Any], key: str, path: str) -> bool:
    value = section.get(key)
    if not isinstance(value, bool):
        raise ConfigValidationError(f"'{path}.{key}' debe ser booleano.")
    return value


def _require_number(section: dict[str, Any], key: str, path: str, minimum: float | None = None) -> float:
    value = section.get(key)
    if not isinstance(value, (int, float)):
        raise ConfigValidationError(f"'{path}.{key}' debe ser numerico.")
    if minimum is not None and value < minimum:
        raise ConfigValidationError(f"'{path}.{key}' debe ser mayor o igual a {minimum}.")
    return float(value)


def _require_string(section: dict[str, Any], key: str, path: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigValidationError(f"'{path}.{key}' debe ser una cadena no vacia.")
    return value


def _require_list(section: dict[str, Any], key: str, path: str) -> list[Any]:
    value = section.get(key)
    if not isinstance(value, list):
        raise ConfigValidationError(f"'{path}.{key}' debe ser una lista.")
    return value


def validar_config(config: dict[str, Any]) -> ValidatedConfig:
    if not isinstance(config, dict):
        raise ConfigValidationError("La configuracion raiz debe ser un objeto.")

    empresa = _require_mapping(config, "empresa")
    _require_string(empresa, "rfc", "empresa")
    _require_string(empresa, "nombre", "empresa")

    notificaciones = _require_mapping(config, "notificaciones")
    email = _require_mapping(notificaciones, "email")
    _require_bool(email, "habilitado", "notificaciones.email")
    _require_string(email, "smtp_server", "notificaciones.email")
    _require_number(email, "smtp_port", "notificaciones.email", minimum=1)
    destinatarios = _require_list(email, "destinatarios", "notificaciones.email")
    if not all(isinstance(item, str) and item.strip() for item in destinatarios):
        raise ConfigValidationError("'notificaciones.email.destinatarios' debe contener correos validos como cadenas.")

    whatsapp = _require_mapping(notificaciones, "whatsapp")
    _require_bool(whatsapp, "habilitado", "notificaciones.whatsapp")

    reglas = _require_mapping(config, "reglas")
    required_rules = (
        "ingreso_alto",
        "concentracion_cliente",
        "tipo_cambio_anomalo",
        "pago_sin_ingreso",
        "vencimientos_sat",
    )
    for rule_name in required_rules:
        rule = _require_mapping(reglas, rule_name)
        _require_bool(rule, "habilitado", f"reglas.{rule_name}")
        if "severidad" in rule:
            _require_string(rule, "severidad", f"reglas.{rule_name}")

    _require_number(reglas["ingreso_alto"], "umbral_mxn", "reglas.ingreso_alto", minimum=0)
    _require_number(reglas["concentracion_cliente"], "porcentaje_maximo", "reglas.concentracion_cliente", minimum=0)
    _require_number(reglas["tipo_cambio_anomalo"], "rango_minimo", "reglas.tipo_cambio_anomalo", minimum=0)
    _require_number(reglas["tipo_cambio_anomalo"], "rango_maximo", "reglas.tipo_cambio_anomalo", minimum=0)
    _require_number(reglas["vencimientos_sat"], "dias_anticipacion", "reglas.vencimientos_sat", minimum=0)

    datos = _require_mapping(config, "datos")
    _require_string(datos, "carpeta_excel", "datos")
    _require_string(datos, "patron_emitidas", "datos")
    _require_string(datos, "patron_recibidas", "datos")

    scheduler = _require_mapping(config, "scheduler")
    _require_bool(scheduler, "habilitado", "scheduler")
    hora = _require_string(scheduler, "hora_revision", "scheduler")
    try:
        datetime.strptime(hora, "%H:%M")
    except ValueError as exc:
        raise ConfigValidationError("'scheduler.hora_revision' debe tener formato HH:MM.") from exc
    dias_semana = _require_list(scheduler, "dias_semana", "scheduler")
    dias_validos = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
    if not dias_semana or any(dia not in dias_validos for dia in dias_semana):
        raise ConfigValidationError("'scheduler.dias_semana' debe contener dias validos como mon..sun.")
    _require_string(scheduler, "timezone", "scheduler")

    reportes = _require_mapping(config, "reportes")
    _require_string(reportes, "carpeta_salida", "reportes")
    _require_bool(reportes, "generar_excel", "reportes")
    _require_bool(reportes, "generar_html", "reportes")
    _require_number(reportes, "retener_dias", "reportes", minimum=0)

    return ValidatedConfig(raw=config)
