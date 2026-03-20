# src/robots/r8_export_excel.py
# R8 — Exporta Excels mensuales (CFDI, CFDI_PUE, Resumen) por RFC y ROL
# Soporta:
#   --rfc <RFC>                 -> un RFC
#   --rfc RFC1,RFC2             -> varios RFCs (coma-separado)
#   --rfc ALL                   -> todos los RFC detectados con XML en ese año/mes
#   --include-empty             -> genera Excel vacío (headers/estilo) si no hay XML
#
# Estructura soportada de bóveda:
#   A) data/boveda/extract/<RFC>/<YYYY>/<MM>/<ROL>/*.xml
#   B) data/boveda/extract/<RFC>/<ROL>/<YYYY>/<MM>/*.xml
#
# Salida SIEMPRE:
#   data/exports/<RFC>/<YYYY-MM>/<RFC>_<YYYY-MM>_<ROL>_Facturas.xlsx

from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import List, Iterable
from src.core.r8_excel_core import (
    build_monthly_excels_from_xml_bytes,
    save_excels_with_format,
)

BOVEDA_DIR = Path("data/boveda/extract")
EXPORTS_DIR = Path("data/exports")


def _list_month_xml_paths_for_base(base: Path) -> List[Path]:
    if base.exists():
        return sorted(base.rglob("*.xml"))
    return []


def _list_month_xml_bytes(rfc: str, year: int, month: int, role: str) -> List[bytes]:
    y = f"{year:04d}"
    m = f"{month:02d}"
    # Variante A y B
    p1 = BOVEDA_DIR / rfc / y / m / role
    p2 = BOVEDA_DIR / rfc / role / y / m
    for base in (p1, p2):
        px = _list_month_xml_paths_for_base(base)
        if px:
            return [p.read_bytes() for p in px]
    return []


def _discover_rfcs(year: int, month: int, roles: Iterable[str]) -> List[str]:
    """Detecta RFCs que tengan al menos un XML en el año/mes indicado (en cualquiera de las dos estructuras)."""
    rfcs: List[str] = []
    if not BOVEDA_DIR.exists():
        return rfcs
    y = f"{year:04d}"
    m = f"{month:02d}"

    for rfc_dir in sorted([p for p in BOVEDA_DIR.iterdir() if p.is_dir()]):
        rfc = rfc_dir.name.upper()
        found = False
        for role in roles:
            # Variante A: RFC/AAAA/MM/ROL
            if _list_month_xml_paths_for_base(BOVEDA_DIR / rfc / y / m / role):
                found = True
                break
            # Variante B: RFC/ROL/AAAA/MM
            if _list_month_xml_paths_for_base(BOVEDA_DIR / rfc / role / y / m):
                found = True
                break
        if found:
            rfcs.append(rfc)
    return rfcs


def _parse_rfc_arg(rfc_arg: str, year: int, month: int, roles: List[str]) -> List[str]:
    """
    - 'ALL'  -> autodetectar RFCs con XML para ese año/mes/roles
    - 'A,B'  -> lista explícita
    - 'X'    -> único RFC
    """
    rfc_arg = (rfc_arg or "").strip()
    if not rfc_arg:
        raise SystemExit("--rfc es obligatorio (usa un RFC, una lista separada por coma, o ALL).")

    if rfc_arg.upper() == "ALL":
        rfcs = _discover_rfcs(year, month, roles)
        if not rfcs:
            raise SystemExit("No se detectaron RFCs con XML en la bóveda para ese período.")
        return rfcs

    if "," in rfc_arg:
        parts = [p.strip().upper() for p in rfc_arg.split(",") if p.strip()]
        if not parts:
            raise SystemExit("Lista de RFCs vacía después de parsear.")
        return parts

    return [rfc_arg.upper()]


def _export_one_rfc_month(rfc: str, year: int, month: int, role: str, include_empty: bool) -> str | None:
    """
    Exporta el Excel mensual para un RFC/ROL.
    - Devuelve la ruta del archivo generado o None si no había XML y include_empty es False.
    """
    blobs = _list_month_xml_bytes(rfc, year, month, role)
    yyyy_mm = f"{year:04d}-{month:02d}"
    out_dir = EXPORTS_DIR / rfc / yyyy_mm
    out_path = out_dir / f"{rfc}_{yyyy_mm}_{role}_Facturas.xlsx"

    sheets = build_monthly_excels_from_xml_bytes(blobs)
    # Si no hay XML y no quieren archivo vacío, omitimos
    has_data = any(not df.empty for df in sheets.values())
    if not has_data and not include_empty:
        return None

    save_excels_with_format(sheets, out_path)
    return str(out_path)


def main():
    ap = argparse.ArgumentParser(
        description="R8 - Exporta Excels mensuales por RFC/ROL (CFDI, CFDI_PUE, Resumen)."
    )
    ap.add_argument("--rfc", required=True,
                    help="RFC | RFC1,RFC2 | ALL (autodetectar).")
    ap.add_argument("--year", type=int, required=True, help="Año (YYYY)")
    ap.add_argument("--month", type=int, required=True, help="Mes (MM)")
    ap.add_argument("--roles", default="RECIBIDAS,EMITIDAS",
                    help="Roles separados por coma. Ej: RECIBIDAS,EMITIDAS")
    ap.add_argument("--include-empty", action="store_true",
                    help="Si se especifica, genera Excel vacío (headers) aunque no haya XML.")
    args = ap.parse_args()

    roles = [r.strip().upper() for r in args.roles.split(",") if r.strip()]
    rfcs = _parse_rfc_arg(args.rfc, args.year, args.month, roles)

    results: list[str] = []
    for rfc in rfcs:
        for role in roles:
            out = _export_one_rfc_month(rfc, args.year, args.month, role, args.include_empty)
            if out:
                results.append(out)

    print(json.dumps({"status": "ok", "files": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
