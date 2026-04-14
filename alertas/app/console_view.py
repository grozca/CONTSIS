from __future__ import annotations

from typing import Any

from .catalog import nombre_cliente
from .models import Alert


def imprimir_resumen(alertas: list[Alert], clientes: dict[str, Any]) -> None:
    colores = {"ALTA": "\033[91m", "MEDIA": "\033[93m", "BAJA": "\033[92m"}
    reset = "\033[0m"
    bold = "\033[1m"

    print(f"\n{bold}{'=' * 65}{reset}")
    print(f"{bold}  CONTSIS v2.0 - Alertas detectadas ({len(alertas)} total){reset}")
    print(f"{bold}{'=' * 65}{reset}")

    rfc_actual = None
    for alerta in alertas:
        if alerta.rfc != rfc_actual:
            rfc_actual = alerta.rfc
            nombre = nombre_cliente(alerta.rfc, clientes)
            print(f"\n  {bold}{nombre} - {alerta.rfc}{reset}")
            print(f"  {'-' * 55}")
        color = colores.get(alerta.severidad, "")
        print(f"  {color}[{alerta.severidad}]{reset} {alerta.tipo_alerta}")
        print(f"    {alerta.resumen}")
        if alerta.monto_total > 0:
            print(f"    Monto: ${alerta.monto_total:,.2f} MXN")

    altas = sum(1 for alerta in alertas if alerta.severidad == "ALTA")
    medias = sum(1 for alerta in alertas if alerta.severidad == "MEDIA")
    bajas = sum(1 for alerta in alertas if alerta.severidad == "BAJA")
    print(
        f"\n{bold}  Resumen: {colores['ALTA']}{altas} ALTA{reset} | "
        f"{colores['MEDIA']}{medias} MEDIA{reset} | "
        f"{colores['BAJA']}{bajas} BAJA{reset}\n"
    )

