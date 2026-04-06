from __future__ import annotations

import logging

import pandas as pd

from app.models import ClientPeriodData
from app.rules import evaluar_cliente_periodo


def build_cfg() -> dict:
    return {
        "reglas": {
            "ingreso_alto": {"habilitado": True, "umbral_mxn": 200000, "severidad": "ALTA"},
            "concentracion_cliente": {"habilitado": True, "porcentaje_maximo": 70, "severidad": "BAJA"},
            "tipo_cambio_anomalo": {"habilitado": True, "rango_minimo": 16.0, "rango_maximo": 22.0, "severidad": "MEDIA"},
            "pago_sin_ingreso": {"habilitado": False, "severidad": "MEDIA"},
        }
    }


def test_evaluar_cliente_periodo_detecta_ingreso_alto() -> None:
    df_emitidas = pd.DataFrame(
        [
            {
                "TIPO_COMPROB": "I",
                "SUBTOTAL_MXN": 300000,
                "UUID": "UUID-1",
                "RECEPTOR_NOMBRE": "Cliente Uno",
                "MONEDA": "MXN",
                "TIPO_CAMBIO": 1,
            }
        ]
    )
    datos = ClientPeriodData(rfc="AAA010101AAA", periodo="2026-03", df_e=df_emitidas, df_r=pd.DataFrame())
    clientes = {"AAA010101AAA": {"nombre_corto": "Empresa Demo"}}

    alertas = evaluar_cliente_periodo(datos, build_cfg(), clientes, logging.getLogger("test"))

    assert len(alertas) == 2
    assert any(alerta.tipo_alerta == "INGRESO_ALTO" for alerta in alertas)

