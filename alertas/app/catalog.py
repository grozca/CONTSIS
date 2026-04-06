from __future__ import annotations

from typing import Any


def nombre_cliente(rfc: str, clientes: dict[str, Any], fallback: str = "") -> str:
    cliente = clientes.get(rfc, {})
    return cliente.get("nombre_corto") or cliente.get("razon_social") or fallback or rfc


def emails_cliente(rfc: str, clientes: dict[str, Any]) -> list[str]:
    return clientes.get(rfc, {}).get("emails", [])
