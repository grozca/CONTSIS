from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from src.analytics.queries import (
        get_monthly_kpis,
        get_monthly_variation,
        get_top_counterparties,
    )
    from src.analytics.schema import DB_PATH, get_connection
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.queries import (
        get_monthly_kpis,
        get_monthly_variation,
        get_top_counterparties,
    )
    from src.analytics.schema import DB_PATH, get_connection


def build_company_month_insights(
    periodo: str,
    rfc_empresa: str,
    previous_periodo: str | None = None,
    top_n: int = 5,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    kpi_rows = get_monthly_kpis(periodo, rfc_empresa=rfc_empresa, db_path=db_path)
    if not kpi_rows:
        raise ValueError(f"No hay KPIs cargados para {rfc_empresa} en {periodo}")

    kpis = kpi_rows[0]
    previous_periodo = previous_periodo or infer_previous_period(periodo)
    variation_rows = get_monthly_variation(periodo, previous_periodo, rfc_empresa=rfc_empresa, db_path=db_path)
    variation = variation_rows[0] if variation_rows else {}

    top_clientes = get_top_counterparties(periodo, rfc_empresa, "EMITIDA", top_n=top_n, db_path=db_path)
    top_proveedores = get_top_counterparties(periodo, rfc_empresa, "RECIBIDA", top_n=top_n, db_path=db_path)
    company_meta = get_company_metadata(rfc_empresa, db_path=db_path)
    risk = compute_risk_profile(kpis, variation, top_clientes, top_proveedores)

    return {
        "empresa": {
            "rfc": rfc_empresa.upper(),
            "razon_social": company_meta.get("razon_social"),
            "nombre_corto": company_meta.get("nombre_corto"),
        },
        "periodo": periodo,
        "periodo_anterior": previous_periodo,
        "kpis": kpis,
        "variation": variation,
        "top_clientes": top_clientes,
        "top_proveedores": top_proveedores,
        "risk": risk,
    }


def get_company_metadata(rfc_empresa: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT razon_social, nombre_corto
            FROM empresas
            WHERE rfc = ?
            """,
            (rfc_empresa.upper(),),
        ).fetchone()
        if not row:
            return {"razon_social": None, "nombre_corto": None}
        return {"razon_social": row[0], "nombre_corto": row[1]}
    finally:
        conn.close()


def compute_risk_profile(
    kpis: dict[str, Any],
    variation: dict[str, Any],
    top_clientes: list[dict[str, Any]],
    top_proveedores: list[dict[str, Any]],
) -> dict[str, Any]:
    score = 0
    signals: list[dict[str, Any]] = []

    ingresos = float(kpis.get("ingresos_mxn") or 0)
    egresos = float(kpis.get("egresos_mxn") or 0)
    num_emitidos = int(kpis.get("num_cfdi_emitidos") or 0)
    num_recibidos = int(kpis.get("num_cfdi_recibidos") or 0)
    num_pagos = int(kpis.get("num_pagos") or 0)

    var_ingresos = variation.get("variacion_ingresos_pct")
    var_egresos = variation.get("variacion_egresos_pct")
    top_cliente_pct = float(top_clientes[0]["porcentaje_del_total"]) if top_clientes else 0.0
    top_proveedor_pct = float(top_proveedores[0]["porcentaje_del_total"]) if top_proveedores else 0.0

    if num_emitidos == 0 and num_recibidos == 0:
        signals.append(_signal("info", "Sin actividad CFDI en el periodo"))

    if ingresos == 0 and egresos > 0:
        score += 35
        signals.append(_signal("high", "Hay egresos sin ingresos identificados en el periodo"))

    if isinstance(var_ingresos, (int, float)) and var_ingresos <= -30:
        score += 30
        signals.append(_signal("high", f"Los ingresos cayeron {abs(var_ingresos):.2f}% vs mes anterior"))

    if isinstance(var_egresos, (int, float)) and var_egresos >= 30:
        score += 20
        signals.append(_signal("medium", f"Los egresos subieron {var_egresos:.2f}% vs mes anterior"))

    if ingresos > 0 and egresos > ingresos * 1.2:
        score += 25
        signals.append(_signal("medium", "Los egresos del periodo superan los ingresos en mas de 20%"))

    if top_cliente_pct >= 45:
        score += 15
        signals.append(_signal("medium", f"Alta concentracion de ingresos en un cliente ({top_cliente_pct:.2f}%)"))

    if top_proveedor_pct >= 35:
        score += 15
        signals.append(_signal("medium", f"Alta concentracion de gasto en un proveedor ({top_proveedor_pct:.2f}%)"))

    if num_recibidos > 0 and num_emitidos == 0:
        score += 10
        signals.append(_signal("medium", "Se detectan CFDI recibidos pero no emitidos"))

    if egresos > 0 and num_pagos == 0:
        score += 10
        signals.append(_signal("low", "Hay egresos registrados sin complementos de pago cargados"))

    score = min(score, 100)
    return {
        "score": score,
        "level": risk_level(score),
        "signals": signals,
        "headline": build_headline(score, signals),
    }


def risk_level(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"


def build_headline(score: int, signals: list[dict[str, Any]]) -> str:
    if not signals:
        return "Operacion estable sin alertas relevantes"
    principal = signals[0]["message"]
    return f"Riesgo {risk_level(score)}: {principal}"


def infer_previous_period(periodo: str) -> str:
    year_str, month_str = periodo.split("-")
    year = int(year_str)
    month = int(month_str)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year:04d}-{month - 1:02d}"


def _signal(severity: str, message: str) -> dict[str, str]:
    return {"severity": severity, "message": message}


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye un resumen ejecutivo por empresa y periodo.")
    parser.add_argument("--yyyy_mm", required=True, help="Periodo a consultar en formato YYYY-MM")
    parser.add_argument("--rfc", required=True, help="RFC de la empresa")
    parser.add_argument("--previous-yyyy_mm", required=False, help="Periodo anterior opcional")
    parser.add_argument("--top-n", type=int, default=5, help="Numero de contrapartes top a incluir")
    parser.add_argument("--db-path", required=False, help="Ruta opcional a analytics.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH
    result = build_company_month_insights(
        periodo=args.yyyy_mm,
        rfc_empresa=args.rfc,
        previous_periodo=args.previous_yyyy_mm,
        top_n=args.top_n,
        db_path=db_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
