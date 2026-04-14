from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from src.analytics.insights import build_company_month_insights, compute_risk_profile
    from src.analytics.schema import DB_PATH, get_connection
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.insights import build_company_month_insights, compute_risk_profile
    from src.analytics.schema import DB_PATH, get_connection


def list_available_companies(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    conn.row_factory = None
    try:
        rows = conn.execute(
            """
            SELECT rfc, COALESCE(nombre_corto, razon_social, rfc) AS nombre
            FROM empresas
            WHERE activo = 1
            ORDER BY nombre
            """
        ).fetchall()
        return [{"rfc": row[0], "nombre": row[1]} for row in rows]
    finally:
        conn.close()


def list_available_periods(rfc_empresa: str | None = None, db_path: Path = DB_PATH) -> list[str]:
    conn = get_connection(db_path)
    try:
        if rfc_empresa:
            rows = conn.execute(
                """
                SELECT DISTINCT periodo
                FROM kpis_mensuales_empresa
                WHERE rfc_empresa = ?
                ORDER BY periodo DESC
                """,
                (rfc_empresa.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT DISTINCT periodo
                FROM kpis_mensuales_empresa
                ORDER BY periodo DESC
                """
            ).fetchall()
        return [row[0] for row in rows]
    finally:
        conn.close()


def list_available_years(rfc_empresa: str | None = None, db_path: Path = DB_PATH) -> list[int]:
    periods = list_available_periods(rfc_empresa=rfc_empresa, db_path=db_path)
    years = sorted({int(period[:4]) for period in periods}, reverse=True)
    return years


def get_company_timeseries(
    rfc_empresa: str,
    db_path: Path = DB_PATH,
    period_start: str | None = None,
    period_end: str | None = None,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    conn.row_factory = None
    try:
        where_parts = ["rfc_empresa = ?"]
        params: list[Any] = [rfc_empresa.upper()]
        if period_start:
            where_parts.append("periodo >= ?")
            params.append(period_start)
        if period_end:
            where_parts.append("periodo <= ?")
            params.append(period_end)

        rows = conn.execute(
            f"""
            SELECT
                periodo,
                ingresos_mxn,
                egresos_mxn,
                num_cfdi_emitidos,
                num_cfdi_recibidos,
                num_pagos,
                ticket_promedio_emitido,
                ticket_promedio_recibido
            FROM kpis_mensuales_empresa
            WHERE {' AND '.join(where_parts)}
            ORDER BY periodo
            """,
            tuple(params),
        ).fetchall()

        timeseries = [
            {
                "periodo": row[0],
                "ingresos_mxn": row[1],
                "egresos_mxn": row[2],
                "num_cfdi_emitidos": row[3],
                "num_cfdi_recibidos": row[4],
                "num_pagos": row[5],
                "ticket_promedio_emitido": row[6],
                "ticket_promedio_recibido": row[7],
            }
            for row in rows
        ]
        return add_cumulative_columns(timeseries)
    finally:
        conn.close()


def add_cumulative_columns(timeseries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ingresos_acum = 0.0
    egresos_acum = 0.0
    balance_acum = 0.0
    emitidos_acum = 0
    recibidos_acum = 0
    pagos_acum = 0

    enriched: list[dict[str, Any]] = []
    for row in timeseries:
        ingresos = float(row.get("ingresos_mxn") or 0)
        egresos = float(row.get("egresos_mxn") or 0)
        balance = ingresos - egresos

        ingresos_acum += ingresos
        egresos_acum += egresos
        balance_acum += balance
        emitidos_acum += int(row.get("num_cfdi_emitidos") or 0)
        recibidos_acum += int(row.get("num_cfdi_recibidos") or 0)
        pagos_acum += int(row.get("num_pagos") or 0)

        enriched.append(
            {
                **row,
                "balance_mxn": round(balance, 2),
                "ingresos_acumulados_mxn": round(ingresos_acum, 2),
                "egresos_acumulados_mxn": round(egresos_acum, 2),
                "balance_acumulado_mxn": round(balance_acum, 2),
                "emitidos_acumulados": emitidos_acum,
                "recibidos_acumulados": recibidos_acum,
                "pagos_acumulados": pagos_acum,
            }
        )
    return enriched


def aggregate_kpis_from_timeseries(timeseries: list[dict[str, Any]]) -> dict[str, Any]:
    if not timeseries:
        return {
            "ingresos_mxn": 0.0,
            "egresos_mxn": 0.0,
            "balance_mxn": 0.0,
            "num_cfdi_emitidos": 0,
            "num_cfdi_recibidos": 0,
            "num_pagos": 0,
            "ticket_promedio_emitido": 0.0,
            "ticket_promedio_recibido": 0.0,
            "ingresos_acumulados_mxn": 0.0,
            "egresos_acumulados_mxn": 0.0,
            "balance_acumulado_mxn": 0.0,
            "periodos_incluidos": 0,
        }

    ingresos = round(sum(float(row.get("ingresos_mxn") or 0) for row in timeseries), 2)
    egresos = round(sum(float(row.get("egresos_mxn") or 0) for row in timeseries), 2)
    emitidos = sum(int(row.get("num_cfdi_emitidos") or 0) for row in timeseries)
    recibidos = sum(int(row.get("num_cfdi_recibidos") or 0) for row in timeseries)
    pagos = sum(int(row.get("num_pagos") or 0) for row in timeseries)

    return {
        "ingresos_mxn": ingresos,
        "egresos_mxn": egresos,
        "balance_mxn": round(ingresos - egresos, 2),
        "num_cfdi_emitidos": emitidos,
        "num_cfdi_recibidos": recibidos,
        "num_pagos": pagos,
        "ticket_promedio_emitido": round((ingresos / emitidos) if emitidos else 0.0, 2),
        "ticket_promedio_recibido": round((egresos / recibidos) if recibidos else 0.0, 2),
        "ingresos_acumulados_mxn": float(timeseries[-1].get("ingresos_acumulados_mxn") or 0),
        "egresos_acumulados_mxn": float(timeseries[-1].get("egresos_acumulados_mxn") or 0),
        "balance_acumulado_mxn": float(timeseries[-1].get("balance_acumulado_mxn") or 0),
        "periodos_incluidos": len(timeseries),
    }


def get_company_metadata(rfc_empresa: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    conn = get_connection(db_path)
    conn.row_factory = None
    try:
        row = conn.execute(
            """
            SELECT rfc, razon_social, nombre_corto
            FROM empresas
            WHERE rfc = ?
            """,
            (rfc_empresa.upper(),),
        ).fetchone()
        if not row:
            return {"rfc": rfc_empresa.upper(), "razon_social": None, "nombre_corto": None}
        return {"rfc": row[0], "razon_social": row[1], "nombre_corto": row[2]}
    finally:
        conn.close()


def get_top_counterparties_for_range(
    rfc_empresa: str,
    rol: str,
    period_start: str,
    period_end: str,
    top_n: int = 10,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    if rol.upper() == "EMITIDA":
        name_expr = "COALESCE(nombre_receptor, rfc_receptor, 'SIN_NOMBRE')"
        rfc_expr = "COALESCE(rfc_receptor, 'SIN_RFC')"
    else:
        name_expr = "COALESCE(nombre_emisor, rfc_emisor, 'SIN_NOMBRE')"
        rfc_expr = "COALESCE(rfc_emisor, 'SIN_RFC')"

    conn = get_connection(db_path)
    try:
        total_mxn = (
            conn.execute(
                """
                SELECT COALESCE(SUM(total_mxn), 0)
                FROM cfdi
                WHERE rfc_empresa = ? AND rol = ? AND periodo >= ? AND periodo <= ?
                """,
                (rfc_empresa.upper(), rol.upper(), period_start, period_end),
            ).fetchone()[0]
            or 0.0
        )

        conn.row_factory = None
        rows = conn.execute(
            f"""
            SELECT
                {name_expr} AS nombre_counterparty,
                {rfc_expr} AS rfc_counterparty,
                COUNT(*) AS num_cfdi,
                ROUND(COALESCE(SUM(total_mxn), 0), 2) AS monto_total_mxn
            FROM cfdi
            WHERE rfc_empresa = ? AND rol = ? AND periodo >= ? AND periodo <= ?
            GROUP BY 1, 2
            ORDER BY monto_total_mxn DESC, num_cfdi DESC
            LIMIT ?
            """,
            (rfc_empresa.upper(), rol.upper(), period_start, period_end, top_n),
        ).fetchall()

        result = []
        for row in rows:
            monto = float(row[3] or 0)
            result.append(
                {
                    "nombre_counterparty": row[0],
                    "rfc_counterparty": row[1],
                    "num_cfdi": row[2],
                    "monto_total_mxn": monto,
                    "porcentaje_del_total": round((monto / total_mxn) * 100, 2) if total_mxn else 0.0,
                }
            )
        return result
    finally:
        conn.close()


def get_company_month_view(rfc_empresa: str, yyyy_mm: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    insights = build_company_month_insights(yyyy_mm, rfc_empresa, db_path=db_path)
    full_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path)
    return {
        "empresa": insights["empresa"],
        "analysis_mode": "monthly",
        "periodo": yyyy_mm,
        "period_label": yyyy_mm,
        "period_start": yyyy_mm,
        "period_end": yyyy_mm,
        "timeseries": full_timeseries,
        "range_timeseries": [row for row in full_timeseries if row["periodo"] == yyyy_mm],
        "summary": {
            **insights["kpis"],
            "balance_mxn": round(float(insights["kpis"]["ingresos_mxn"]) - float(insights["kpis"]["egresos_mxn"]), 2),
            "periodos_incluidos": 1,
        },
        "comparison": insights["variation"],
        "top_clientes": insights["top_clientes"],
        "top_proveedores": insights["top_proveedores"],
        "insights": insights,
    }


def get_company_ytd_view(
    rfc_empresa: str,
    year: int,
    month_cutoff: int,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    period_start = f"{year:04d}-01"
    period_end = f"{year:04d}-{month_cutoff:02d}"
    range_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path, period_start=period_start, period_end=period_end)
    full_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path)
    summary = aggregate_kpis_from_timeseries(range_timeseries)

    previous_end = f"{year - 1:04d}-{month_cutoff:02d}"
    previous_timeseries = get_company_timeseries(
        rfc_empresa,
        db_path=db_path,
        period_start=f"{year - 1:04d}-01",
        period_end=previous_end,
    )
    previous_summary = aggregate_kpis_from_timeseries(previous_timeseries)
    comparison = build_range_comparison(summary, previous_summary, f"{year - 1:04d}-YTD-{month_cutoff:02d}")

    top_clientes = get_top_counterparties_for_range(rfc_empresa, "EMITIDA", period_start, period_end, db_path=db_path)
    top_proveedores = get_top_counterparties_for_range(rfc_empresa, "RECIBIDA", period_start, period_end, db_path=db_path)
    risk = compute_risk_profile(summary, comparison, top_clientes, top_proveedores)
    empresa = get_company_metadata(rfc_empresa, db_path=db_path)

    return {
        "empresa": empresa,
        "analysis_mode": "ytd",
        "periodo": period_end,
        "period_label": f"YTD {year:04d} al mes {month_cutoff:02d}",
        "period_start": period_start,
        "period_end": period_end,
        "timeseries": full_timeseries,
        "range_timeseries": range_timeseries,
        "summary": summary,
        "comparison": comparison,
        "top_clientes": top_clientes,
        "top_proveedores": top_proveedores,
        "insights": {
            "empresa": empresa,
            "periodo": period_end,
            "periodo_anterior": previous_end,
            "kpis": summary,
            "variation": comparison,
            "top_clientes": top_clientes,
            "top_proveedores": top_proveedores,
            "risk": risk,
        },
    }


def get_company_year_view(rfc_empresa: str, year: int, db_path: Path = DB_PATH) -> dict[str, Any]:
    period_start = f"{year:04d}-01"
    period_end = f"{year:04d}-12"
    range_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path, period_start=period_start, period_end=period_end)
    full_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path)
    summary = aggregate_kpis_from_timeseries(range_timeseries)

    previous_start = f"{year - 1:04d}-01"
    previous_end = f"{year - 1:04d}-12"
    previous_timeseries = get_company_timeseries(rfc_empresa, db_path=db_path, period_start=previous_start, period_end=previous_end)
    previous_summary = aggregate_kpis_from_timeseries(previous_timeseries)
    comparison = build_range_comparison(summary, previous_summary, f"{year - 1:04d}")

    top_clientes = get_top_counterparties_for_range(rfc_empresa, "EMITIDA", period_start, period_end, db_path=db_path)
    top_proveedores = get_top_counterparties_for_range(rfc_empresa, "RECIBIDA", period_start, period_end, db_path=db_path)
    risk = compute_risk_profile(summary, comparison, top_clientes, top_proveedores)
    empresa = get_company_metadata(rfc_empresa, db_path=db_path)

    return {
        "empresa": empresa,
        "analysis_mode": "year",
        "periodo": str(year),
        "period_label": f"Año {year:04d}",
        "period_start": period_start,
        "period_end": period_end,
        "timeseries": full_timeseries,
        "range_timeseries": range_timeseries,
        "summary": summary,
        "comparison": comparison,
        "top_clientes": top_clientes,
        "top_proveedores": top_proveedores,
        "insights": {
            "empresa": empresa,
            "periodo": str(year),
            "periodo_anterior": str(year - 1),
            "kpis": summary,
            "variation": comparison,
            "top_clientes": top_clientes,
            "top_proveedores": top_proveedores,
            "risk": risk,
        },
    }


def build_range_comparison(
    current_summary: dict[str, Any],
    previous_summary: dict[str, Any],
    previous_label: str,
) -> dict[str, Any]:
    has_previous = bool(previous_summary.get("periodos_incluidos"))
    previous_ingresos = previous_summary.get("ingresos_mxn") if has_previous else None
    previous_egresos = previous_summary.get("egresos_mxn") if has_previous else None
    previous_emitidos = previous_summary.get("num_cfdi_emitidos") if has_previous else None
    previous_recibidos = previous_summary.get("num_cfdi_recibidos") if has_previous else None
    previous_ticket_emitido = previous_summary.get("ticket_promedio_emitido") if has_previous else None
    previous_ticket_recibido = previous_summary.get("ticket_promedio_recibido") if has_previous else None

    return {
        "periodo_actual": "RANGE",
        "periodo_anterior": previous_label if has_previous else None,
        "ingresos_actual": current_summary["ingresos_mxn"],
        "ingresos_anterior": previous_ingresos,
        "egresos_actual": current_summary["egresos_mxn"],
        "egresos_anterior": previous_egresos,
        "emitidos_actual": current_summary["num_cfdi_emitidos"],
        "emitidos_anterior": previous_emitidos,
        "recibidos_actual": current_summary["num_cfdi_recibidos"],
        "recibidos_anterior": previous_recibidos,
        "ticket_emitido_actual": current_summary["ticket_promedio_emitido"],
        "ticket_emitido_anterior": previous_ticket_emitido,
        "ticket_recibido_actual": current_summary["ticket_promedio_recibido"],
        "ticket_recibido_anterior": previous_ticket_recibido,
        "variacion_ingresos_pct": _pct_change(current_summary["ingresos_mxn"], previous_ingresos),
        "variacion_egresos_pct": _pct_change(current_summary["egresos_mxn"], previous_egresos),
        "variacion_emitidos_pct": _pct_change(current_summary["num_cfdi_emitidos"], previous_emitidos),
        "variacion_recibidos_pct": _pct_change(current_summary["num_cfdi_recibidos"], previous_recibidos),
        "variacion_ticket_emitido_pct": _pct_change(current_summary["ticket_promedio_emitido"], previous_ticket_emitido),
        "variacion_ticket_recibido_pct": _pct_change(current_summary["ticket_promedio_recibido"], previous_ticket_recibido),
    }


def get_dashboard_dataset(
    periodo: str,
    rfc_empresa: str,
    db_path: Path = DB_PATH,
    analysis_mode: str = "monthly",
    year: int | None = None,
    month_cutoff: int | None = None,
) -> dict[str, Any]:
    mode = analysis_mode.lower()
    if mode == "monthly":
        return get_company_month_view(rfc_empresa, periodo, db_path=db_path)
    if mode == "ytd":
        if year is None or month_cutoff is None:
            year, month_cutoff = _parse_period(periodo)
        return get_company_ytd_view(rfc_empresa, year, month_cutoff, db_path=db_path)
    if mode == "year":
        if year is None:
            year = int(periodo[:4])
        return get_company_year_view(rfc_empresa, year, db_path=db_path)
    raise ValueError(f"analysis_mode no soportado: {analysis_mode}")


def _parse_period(periodo: str) -> tuple[int, int]:
    year_str, month_str = periodo.split("-")
    return int(year_str), int(month_str)


def _pct_change(actual: Any, previous: Any) -> float | None:
    actual_num = float(actual or 0)
    if previous is None:
        return None
    previous_num = float(previous or 0)
    if previous_num == 0:
        return None if actual_num == 0 else 100.0
    return round(((actual_num - previous_num) / previous_num) * 100, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Datasets para dashboard analitico.")
    parser.add_argument(
        "--query",
        required=True,
        choices=["companies", "periods", "years", "timeseries", "dataset", "month_view", "ytd_view", "year_view"],
    )
    parser.add_argument("--rfc", required=False, help="RFC de la empresa")
    parser.add_argument("--yyyy_mm", required=False, help="Periodo YYYY-MM")
    parser.add_argument("--year", required=False, type=int, help="Anio YYYY")
    parser.add_argument("--month-cutoff", required=False, type=int, help="Mes de corte para YTD")
    parser.add_argument("--mode", required=False, choices=["monthly", "ytd", "year"], help="Modo para --query dataset")
    parser.add_argument("--db-path", required=False, help="Ruta opcional a analytics.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH

    if args.query == "companies":
        result = list_available_companies(db_path=db_path)
    elif args.query == "periods":
        result = list_available_periods(rfc_empresa=args.rfc, db_path=db_path)
    elif args.query == "years":
        result = list_available_years(rfc_empresa=args.rfc, db_path=db_path)
    elif args.query == "timeseries":
        if not args.rfc:
            raise SystemExit("--rfc es obligatorio para --query timeseries")
        result = get_company_timeseries(args.rfc, db_path=db_path)
    elif args.query == "month_view":
        if not args.rfc or not args.yyyy_mm:
            raise SystemExit("--rfc y --yyyy_mm son obligatorios para --query month_view")
        result = get_company_month_view(args.rfc, args.yyyy_mm, db_path=db_path)
    elif args.query == "ytd_view":
        if not args.rfc or args.year is None or args.month_cutoff is None:
            raise SystemExit("--rfc, --year y --month-cutoff son obligatorios para --query ytd_view")
        result = get_company_ytd_view(args.rfc, args.year, args.month_cutoff, db_path=db_path)
    elif args.query == "year_view":
        if not args.rfc or args.year is None:
            raise SystemExit("--rfc y --year son obligatorios para --query year_view")
        result = get_company_year_view(args.rfc, args.year, db_path=db_path)
    else:
        if not args.rfc or not args.yyyy_mm:
            raise SystemExit("--rfc y --yyyy_mm son obligatorios para --query dataset")
        result = get_dashboard_dataset(
            args.yyyy_mm,
            args.rfc,
            db_path=db_path,
            analysis_mode=args.mode or "monthly",
            year=args.year,
            month_cutoff=args.month_cutoff,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
