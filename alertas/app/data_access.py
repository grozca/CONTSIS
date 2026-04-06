from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from .models import ClientPeriodData
from .settings import PATHS


def leer_excel(path: Path, logger: logging.Logger, hoja: str = "CFDI") -> pd.DataFrame:
    try:
        dataframe = pd.read_excel(path, sheet_name=hoja)
        if "FECHA" in dataframe.columns:
            dataframe["FECHA"] = pd.to_datetime(dataframe["FECHA"], errors="coerce")
        return dataframe
    except Exception as exc:
        logger.warning("No se pudo leer %s hoja %s: %s", path.name, hoja, exc)
        return pd.DataFrame()


def descubrir_periodos(rfc: str) -> list[str]:
    carpeta = PATHS.exports_dir / rfc
    if not carpeta.exists():
        return []
    return sorted(path.name for path in carpeta.iterdir() if path.is_dir())


def cargar_datos_cliente_periodo(rfc: str, periodo: str, logger: logging.Logger) -> ClientPeriodData:
    base = PATHS.exports_dir / rfc / periodo
    path_emitidas = base / f"{rfc}_{periodo}_EMITIDAS_Facturas.xlsx"
    path_recibidas = base / f"{rfc}_{periodo}_RECIBIDAS_Facturas.xlsx"

    df_emitidas = leer_excel(path_emitidas, logger) if path_emitidas.exists() else pd.DataFrame()
    df_recibidas = leer_excel(path_recibidas, logger) if path_recibidas.exists() else pd.DataFrame()

    return ClientPeriodData(rfc=rfc, periodo=periodo, df_e=df_emitidas, df_r=df_recibidas)


def descubrir_todos_los_rfcs_con_periodo(periodo: str) -> list[str]:
    if not PATHS.exports_dir.exists():
        return []

    rfcs: list[str] = []
    for rfc_dir in sorted(PATHS.exports_dir.iterdir()):
        if not rfc_dir.is_dir():
            continue
        base = rfc_dir / periodo
        tiene_emitidas = (base / f"{rfc_dir.name}_{periodo}_EMITIDAS_Facturas.xlsx").exists()
        tiene_recibidas = (base / f"{rfc_dir.name}_{periodo}_RECIBIDAS_Facturas.xlsx").exists()
        if tiene_emitidas or tiene_recibidas:
            rfcs.append(rfc_dir.name)
    return rfcs
