from __future__ import annotations

from alertas.app.models import Alert
from alertas.app.rendering import hash_alertas


def test_hash_alertas_is_stable_for_same_payload() -> None:
    alertas_a = [
        Alert(
            rfc="AAA010101AAA",
            nombre="Empresa",
            periodo="2026-03",
            tipo_alerta="INGRESO_ALTO",
            severidad="ALTA",
            resumen="resumen",
            detalle="detalle",
            cantidad=2,
            monto_total=100.0,
        )
    ]
    alertas_b = [
        Alert(
            rfc="AAA010101AAA",
            nombre="Empresa",
            periodo="2026-03",
            tipo_alerta="INGRESO_ALTO",
            severidad="ALTA",
            resumen="otro resumen",
            detalle="otro detalle",
            cantidad=2,
            monto_total=100.0,
        )
    ]

    assert hash_alertas(alertas_a) == hash_alertas(alertas_b)
