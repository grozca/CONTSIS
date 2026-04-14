from __future__ import annotations

from alertas.app.config_validation import ConfigValidationError, validar_config


def build_valid_config() -> dict:
    return {
        "empresa": {"rfc": "AAA010101AAA", "nombre": "Empresa Demo"},
        "notificaciones": {
            "email": {
                "habilitado": True,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "remitente": "demo@example.com",
                "destinatarios": ["demo@example.com"],
                "asunto_prefijo": "[ALERTA]",
            },
            "whatsapp": {"habilitado": False},
        },
        "reglas": {
            "ingreso_alto": {"habilitado": True, "umbral_mxn": 200000, "tipos_comprob": ["I"], "severidad": "ALTA"},
            "concentracion_cliente": {"habilitado": True, "porcentaje_maximo": 70, "severidad": "BAJA"},
            "tipo_cambio_anomalo": {"habilitado": True, "rango_minimo": 16.0, "rango_maximo": 22.0, "severidad": "MEDIA"},
            "pago_sin_ingreso": {"habilitado": True, "ventana_dias": 60, "severidad": "MEDIA"},
            "vencimientos_sat": {"habilitado": True, "dias_anticipacion": 5, "severidad": "MEDIA"},
        },
        "datos": {
            "carpeta_excel": "data/exports",
            "patron_emitidas": "**/*EMITIDAS_Facturas.xlsx",
            "patron_recibidas": "**/*RECIBIDAS_Facturas.xlsx",
        },
        "scheduler": {
            "habilitado": True,
            "hora_revision": "08:00",
            "dias_semana": ["mon", "tue", "wed", "thu", "fri"],
            "timezone": "America/Mexico_City",
        },
    }


def test_valid_config_passes() -> None:
    cfg = build_valid_config()
    validated = validar_config(cfg)
    assert validated.raw["empresa"]["rfc"] == "AAA010101AAA"


def test_invalid_scheduler_hour_fails() -> None:
    cfg = build_valid_config()
    cfg["scheduler"]["hora_revision"] = "25:99"
    try:
        validar_config(cfg)
    except ConfigValidationError as exc:
        assert "hora_revision" in str(exc)
    else:
        raise AssertionError("Se esperaba ConfigValidationError")
