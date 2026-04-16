from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.core.r8_excel_core import (
    COLUMNS,
    COLUMNS_PAGOS,
    _blank_duplicate_monto_pagado,
    _build_resumen,
    build_monthly_excels_from_xml_bytes,
    save_excels_with_format,
)
from src.utils.config import settings


def _boveda_dir() -> Path:
    return Path(settings.boveda_dir) / "extract"


def _exports_dir() -> Path:
    return Path(settings.exports_dir)


def _list_month_xml_paths_for_base(base: Path) -> list[Path]:
    if base.exists():
        return sorted(base.rglob("*.xml"))
    return []


def _list_month_xml_bytes(rfc: str, year: int, month: int, role: str) -> list[bytes]:
    y = f"{year:04d}"
    m = f"{month:02d}"
    boveda_dir = _boveda_dir()
    path_variants = (
        boveda_dir / rfc / y / m / role,
        boveda_dir / rfc / role / y / m,
    )
    for base in path_variants:
        xml_paths = _list_month_xml_paths_for_base(base)
        if xml_paths:
            return [path.read_bytes() for path in xml_paths]
    return []


def _discover_rfcs(year: int, month: int, roles: Iterable[str]) -> list[str]:
    rfcs: list[str] = []
    boveda_dir = _boveda_dir()
    if not boveda_dir.exists():
        return rfcs

    y = f"{year:04d}"
    m = f"{month:02d}"
    for rfc_dir in sorted(path for path in boveda_dir.iterdir() if path.is_dir()):
        rfc = rfc_dir.name.upper()
        if any(
            _list_month_xml_paths_for_base(boveda_dir / rfc / y / m / role)
            or _list_month_xml_paths_for_base(boveda_dir / rfc / role / y / m)
            for role in roles
        ):
            rfcs.append(rfc)
    return rfcs


def _parse_rfc_arg(rfc_arg: str, year: int, month: int, roles: list[str]) -> list[str]:
    rfc_arg = (rfc_arg or "").strip()
    if not rfc_arg:
        raise SystemExit("--rfc es obligatorio (usa un RFC, una lista separada por coma, o ALL).")

    if rfc_arg.upper() == "ALL":
        rfcs = _discover_rfcs(year, month, roles)
        if not rfcs:
            raise SystemExit("No se detectaron RFCs con XML en la boveda para ese periodo.")
        return rfcs

    if "," in rfc_arg:
        rfcs = [part.strip().upper() for part in rfc_arg.split(",") if part.strip()]
        if not rfcs:
            raise SystemExit("Lista de RFCs vacia despues de parsear.")
        return rfcs

    return [rfc_arg.upper()]


def _empty_sheets() -> dict[str, pd.DataFrame]:
    return {
        "CFDI": pd.DataFrame(columns=COLUMNS),
        "CFDI_PUE": pd.DataFrame(columns=COLUMNS),
        "PAGOS": pd.DataFrame(columns=COLUMNS_PAGOS),
        "Resumen": _build_resumen(pd.DataFrame(columns=COLUMNS), pd.DataFrame(columns=COLUMNS)),
    }


def _normalize_date_column(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce")
    normalized = parsed.dt.strftime("%Y-%m-%d")
    fallback = series.astype("string").str.strip().str[:10]
    return normalized.fillna(fallback)


def _normalize_cfdi_frame(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy() if frame is not None else pd.DataFrame()
    for column in COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    df = df.reindex(columns=COLUMNS)
    df["UUID"] = df["UUID"].astype("string").fillna("").str.strip().str.upper()
    df = df[df["UUID"] != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df["FECHA"] = _normalize_date_column(df["FECHA"])
    df = (
        df.assign(_ord=df["FECHA"].astype("string").fillna(""))
        .drop_duplicates(subset=["UUID"], keep="last")
        .sort_values(["_ord", "UUID"])
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )
    return df


def _normalize_pagos_frame(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy() if frame is not None else pd.DataFrame()
    for column in COLUMNS_PAGOS:
        if column not in df.columns:
            df[column] = pd.NA
    df = df.reindex(columns=COLUMNS_PAGOS)
    df["UUID_PAGO"] = df["UUID_PAGO"].astype("string").fillna("").str.strip().str.upper()
    df["UUID_FACTURA_RELACIONADA"] = (
        df["UUID_FACTURA_RELACIONADA"].astype("string").fillna("").str.strip().str.upper()
    )
    df = df[df["UUID_PAGO"] != ""].copy()
    if df.empty:
        return pd.DataFrame(columns=COLUMNS_PAGOS)
    df["FECHA_PAGO"] = _normalize_date_column(df["FECHA_PAGO"])
    df = (
        df.assign(_ord=df["FECHA_PAGO"].astype("string").fillna(""))
        .drop_duplicates(subset=["UUID_PAGO", "UUID_FACTURA_RELACIONADA"], keep="last")
        .sort_values(["_ord", "UUID_PAGO", "UUID_FACTURA_RELACIONADA"], na_position="last")
        .drop(columns=["_ord"])
        .reset_index(drop=True)
    )
    df = _blank_duplicate_monto_pagado(df)
    return df.reindex(columns=COLUMNS_PAGOS)


def _load_existing_sheets(out_path: Path) -> dict[str, pd.DataFrame]:
    if not out_path.exists():
        return _empty_sheets()

    try:
        book = pd.read_excel(out_path, sheet_name=None)
    except Exception:
        return _empty_sheets()

    return {
        "CFDI": _normalize_cfdi_frame(book.get("CFDI", pd.DataFrame())),
        "CFDI_PUE": _normalize_cfdi_frame(book.get("CFDI_PUE", pd.DataFrame())),
        "PAGOS": _normalize_pagos_frame(book.get("PAGOS", pd.DataFrame())),
        "Resumen": book.get("Resumen", pd.DataFrame()),
    }


def _merge_cfdi_frames(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([existing, fresh], ignore_index=True)
    return _normalize_cfdi_frame(merged)


def _merge_pagos_frames(existing: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame:
    merged = pd.concat([existing, fresh], ignore_index=True)
    return _normalize_pagos_frame(merged)


def _build_combined_sheets(existing: dict[str, pd.DataFrame], fresh: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    cfdi = _merge_cfdi_frames(existing["CFDI"], _normalize_cfdi_frame(fresh["CFDI"]))
    pagos = _merge_pagos_frames(existing["PAGOS"], _normalize_pagos_frame(fresh["PAGOS"]))
    cfdi_pue = _normalize_cfdi_frame(
        cfdi[cfdi["METODO_PAGO"].astype("string").str.upper().eq("PUE")].copy()
        if not cfdi.empty
        else pd.DataFrame(columns=COLUMNS)
    )
    resumen = _build_resumen(cfdi, cfdi_pue)
    return {
        "CFDI": cfdi,
        "CFDI_PUE": cfdi_pue,
        "PAGOS": pagos,
        "Resumen": resumen,
    }


def _frame_signature(frame: pd.DataFrame) -> tuple[int, ...]:
    if frame.empty:
        return ()
    normalized = frame.copy().fillna("")
    return tuple(pd.util.hash_pandas_object(normalized, index=False).tolist())


def _sheet_identity(sheets: dict[str, pd.DataFrame]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return _frame_signature(sheets["CFDI"]), _frame_signature(sheets["PAGOS"])


def _fresh_has_data(sheets: dict[str, pd.DataFrame]) -> bool:
    return any(not sheets[name].empty for name in ("CFDI", "CFDI_PUE", "PAGOS"))


def _export_one_rfc_month(rfc: str, year: int, month: int, role: str, include_empty: bool) -> str | None:
    blobs = _list_month_xml_bytes(rfc, year, month, role)
    yyyy_mm = f"{year:04d}-{month:02d}"
    out_dir = _exports_dir() / rfc / yyyy_mm
    out_path = out_dir / f"{rfc}_{yyyy_mm}_{role}_Facturas.xlsx"

    fresh_sheets = build_monthly_excels_from_xml_bytes(blobs, role=role)
    fresh_sheets["CFDI"] = _normalize_cfdi_frame(fresh_sheets["CFDI"])
    fresh_sheets["CFDI_PUE"] = _normalize_cfdi_frame(fresh_sheets["CFDI_PUE"])
    fresh_sheets["PAGOS"] = _normalize_pagos_frame(fresh_sheets["PAGOS"])
    fresh_sheets["Resumen"] = _build_resumen(fresh_sheets["CFDI"], fresh_sheets["CFDI_PUE"])

    if not _fresh_has_data(fresh_sheets):
        if out_path.exists():
            return str(out_path)
        if not include_empty:
            return None
        save_excels_with_format(_empty_sheets(), out_path)
        return str(out_path)

    existing_sheets = _load_existing_sheets(out_path)
    combined_sheets = _build_combined_sheets(existing_sheets, fresh_sheets)

    if out_path.exists() and _sheet_identity(existing_sheets) == _sheet_identity(combined_sheets):
        return str(out_path)

    save_excels_with_format(combined_sheets, out_path)
    return str(out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="R8 - Exporta Excels mensuales por RFC/ROL y los actualiza sin duplicar UUIDs.",
    )
    parser.add_argument("--rfc", required=True, help="RFC | RFC1,RFC2 | ALL (autodetectar).")
    parser.add_argument("--year", type=int, required=True, help="Anio (YYYY)")
    parser.add_argument("--month", type=int, required=True, help="Mes (MM)")
    parser.add_argument(
        "--roles",
        default="RECIBIDAS,EMITIDAS",
        help="Roles separados por coma. Ej: RECIBIDAS,EMITIDAS",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Si se especifica, genera Excel vacio aunque no haya XML.",
    )
    args = parser.parse_args()

    roles = [role.strip().upper() for role in args.roles.split(",") if role.strip()]
    rfcs = _parse_rfc_arg(args.rfc, args.year, args.month, roles)

    results: list[str] = []
    for rfc in rfcs:
        for role in roles:
            output = _export_one_rfc_month(rfc, args.year, args.month, role, args.include_empty)
            if output:
                results.append(output)

    print(json.dumps({"status": "ok", "files": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
