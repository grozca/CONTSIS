from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime_paths import asset_path, bundle_root, config_path, data_path, load_project_env

load_project_env()
BASE_DIR = bundle_root()
DATA_DIR = data_path()
EXPORTS_DIR = data_path("exports")
CLIENTES_PATH = config_path("data", "config", "clientes.json")
CLIENTES_EXAMPLE_PATH = asset_path("data", "config", "clientes.example.json")


@dataclass
class ClienteInfo:
    rfc: str
    razon_social: str | None = None
    nombre_corto: str | None = None
    activo: bool = True
    raw: dict[str, Any] | None = None


@dataclass
class PeriodoFiles:
    rfc: str
    periodo: str
    base_dir: Path
    emitidas_excel: Path | None = None
    recibidas_excel: Path | None = None
    resumen_word: Path | None = None
    manifest: Path | None = None


def load_clientes(clientes_path: Path = CLIENTES_PATH) -> dict[str, ClienteInfo]:
    """
    Carga el catálogo de clientes desde clientes.json.

    Regresa un diccionario indexado por RFC.
    """
    if not clientes_path.exists():
        example_hint = f" Usa {CLIENTES_EXAMPLE_PATH} como base." if CLIENTES_EXAMPLE_PATH.exists() else ""
        raise FileNotFoundError(f"No existe clientes.json en: {clientes_path}.{example_hint}")

    with clientes_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    clientes: dict[str, ClienteInfo] = {}

    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = []
        for item in data:
            if isinstance(item, dict):
                rfc = str(item.get("rfc", "")).strip().upper()
                if rfc:
                    items.append((rfc, item))
    else:
        raise ValueError("clientes.json debe ser una lista o un diccionario.")

    for rfc_key, payload in items:
        if not isinstance(payload, dict):
            continue

        rfc = str(payload.get("rfc", rfc_key)).strip().upper()
        if not rfc:
            continue

        razon_social = _first_non_empty(
            payload.get("razon_social"),
            payload.get("nombre"),
            payload.get("empresa"),
        )
        nombre_corto = _first_non_empty(
            payload.get("nombre_corto"),
            payload.get("alias"),
            payload.get("nombre"),
        )

        activo_raw = payload.get("activo", True)
        activo = bool(activo_raw)

        clientes[rfc] = ClienteInfo(
            rfc=rfc,
            razon_social=razon_social,
            nombre_corto=nombre_corto,
            activo=activo,
            raw=payload,
        )

    return clientes


def discover_period_files(
    yyyy_mm: str,
    exports_dir: Path = EXPORTS_DIR,
) -> list[PeriodoFiles]:
    """
    Busca archivos por RFC para un periodo específico dentro de data/exports.

    Estructura esperada:
    data/exports/<RFC>/<YYYY-MM>/
    """
    validate_period(yyyy_mm)

    if not exports_dir.exists():
        raise FileNotFoundError(f"No existe la carpeta exports: {exports_dir}")

    results: list[PeriodoFiles] = []

    for rfc_dir in sorted(p for p in exports_dir.iterdir() if p.is_dir()):
        rfc = rfc_dir.name.strip().upper()
        periodo_dir = rfc_dir / yyyy_mm

        if not periodo_dir.exists() or not periodo_dir.is_dir():
            continue

        periodo_files = PeriodoFiles(
            rfc=rfc,
            periodo=yyyy_mm,
            base_dir=periodo_dir,
            emitidas_excel=find_first_match(periodo_dir, ["*EMITIDAS*.xlsx"]),
            recibidas_excel=find_first_match(periodo_dir, ["*RECIBIDAS*.xlsx"]),
            resumen_word=find_first_match(periodo_dir, ["*.docx"]),
            manifest=find_first_match(periodo_dir, ["*manifest*.json", "*.manifest.json"]),
        )

        if periodo_files.emitidas_excel or periodo_files.recibidas_excel:
            results.append(periodo_files)

    return results


def build_company_period_context(
    yyyy_mm: str,
    clientes_path: Path = CLIENTES_PATH,
    exports_dir: Path = EXPORTS_DIR,
) -> list[dict[str, Any]]:
    """
    Une catálogo de clientes + archivos descubiertos del periodo.

    Regresa una lista de contextos por RFC-periodo, lista para usar en transforms
    e inserción a DB.
    """
    clientes = load_clientes(clientes_path)
    discovered = discover_period_files(yyyy_mm, exports_dir)

    contexts: list[dict[str, Any]] = []

    for item in discovered:
        cliente = clientes.get(item.rfc)

        contexts.append(
            {
                "rfc": item.rfc,
                "periodo": item.periodo,
                "base_dir": item.base_dir,
                "emitidas_excel": item.emitidas_excel,
                "recibidas_excel": item.recibidas_excel,
                "resumen_word": item.resumen_word,
                "manifest": item.manifest,
                "cliente": cliente,
                "razon_social": cliente.razon_social if cliente else None,
                "nombre_corto": cliente.nombre_corto if cliente else None,
                "activo": cliente.activo if cliente else True,
            }
        )

    return contexts


def find_first_match(base_dir: Path, patterns: list[str]) -> Path | None:
    """
    Regresa la primera coincidencia encontrada entre varios patrones.
    """
    for pattern in patterns:
        matches = sorted(
            p for p in base_dir.glob(pattern)
            if p.is_file() and not p.name.startswith("~$")
        )
        if matches:
            return matches[0]
    return None


def validate_period(yyyy_mm: str) -> None:
    """
    Valida formato YYYY-MM básico.
    """
    parts = yyyy_mm.split("-")
    if len(parts) != 2:
        raise ValueError(f"Periodo inválido: {yyyy_mm}. Usa formato YYYY-MM.")

    year, month = parts
    if len(year) != 4 or not year.isdigit():
        raise ValueError(f"Año inválido en periodo: {yyyy_mm}")

    if len(month) != 2 or not month.isdigit():
        raise ValueError(f"Mes inválido en periodo: {yyyy_mm}")

    month_int = int(month)
    if month_int < 1 or month_int > 12:
        raise ValueError(f"Mes fuera de rango en periodo: {yyyy_mm}")


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


if __name__ == "__main__":
    periodo_demo = "2026-03"
    try:
        contexts = build_company_period_context(periodo_demo)
        print(f"Empresas detectadas para {periodo_demo}: {len(contexts)}")
        for c in contexts:
            print("-" * 60)
            print(f"RFC: {c['rfc']}")
            print(f"Periodo: {c['periodo']}")
            print(f"Nombre corto: {c['nombre_corto']}")
            print(f"Razón social: {c['razon_social']}")
            print(f"Emitidas: {c['emitidas_excel']}")
            print(f"Recibidas: {c['recibidas_excel']}")
    except Exception as e:
        print(f"Error en loader: {e}")
