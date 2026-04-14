from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

try:
    from src.analytics.schema import DB_PATH, get_connection
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.analytics.schema import DB_PATH, get_connection


def _fetch_all_dicts(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_monthly_kpis(
    periodo: str,
    rfc_empresa: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        if rfc_empresa:
            return _fetch_all_dicts(
                conn,
                """
                SELECT
                    rfc_empresa,
                    periodo,
                    ingresos_mxn,
                    egresos_mxn,
                    num_cfdi_emitidos,
                    num_cfdi_recibidos,
                    num_pagos,
                    ticket_promedio_emitido,
                    ticket_promedio_recibido
                FROM kpis_mensuales_empresa
                WHERE periodo = ? AND rfc_empresa = ?
                ORDER BY rfc_empresa
                """,
                (periodo, rfc_empresa.upper()),
            )
        return _fetch_all_dicts(
            conn,
            """
            SELECT
                rfc_empresa,
                periodo,
                ingresos_mxn,
                egresos_mxn,
                num_cfdi_emitidos,
                num_cfdi_recibidos,
                num_pagos,
                ticket_promedio_emitido,
                ticket_promedio_recibido
            FROM kpis_mensuales_empresa
            WHERE periodo = ?
            ORDER BY ingresos_mxn DESC, rfc_empresa
            """,
            (periodo,),
        )
    finally:
        conn.close()


def get_top_counterparties(
    periodo: str,
    rfc_empresa: str,
    rol: str,
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
        total_query = """
            SELECT COALESCE(SUM(total_mxn), 0)
            FROM cfdi
            WHERE periodo = ? AND rfc_empresa = ? AND rol = ?
        """
        total_mxn = conn.execute(total_query, (periodo, rfc_empresa.upper(), rol.upper())).fetchone()[0] or 0.0

        rows = _fetch_all_dicts(
            conn,
            f"""
            SELECT
                {name_expr} AS nombre_counterparty,
                {rfc_expr} AS rfc_counterparty,
                COUNT(*) AS num_cfdi,
                ROUND(COALESCE(SUM(total_mxn), 0), 2) AS monto_total_mxn
            FROM cfdi
            WHERE periodo = ? AND rfc_empresa = ? AND rol = ?
            GROUP BY 1, 2
            ORDER BY monto_total_mxn DESC, num_cfdi DESC
            LIMIT ?
            """,
            (periodo, rfc_empresa.upper(), rol.upper(), top_n),
        )

        for row in rows:
            row["porcentaje_del_total"] = round((row["monto_total_mxn"] / total_mxn) * 100, 2) if total_mxn else 0.0
        return rows
    finally:
        conn.close()


def get_monthly_variation(
    periodo_actual: str,
    periodo_anterior: str,
    rfc_empresa: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    try:
        filtro_rfc = "AND actual.rfc_empresa = ?" if rfc_empresa else ""
        params: list[Any] = [periodo_actual, periodo_anterior]
        if rfc_empresa:
            params.append(rfc_empresa.upper())

        rows = _fetch_all_dicts(
            conn,
            f"""
            SELECT
                actual.rfc_empresa,
                actual.periodo AS periodo_actual,
                previo.periodo AS periodo_anterior,
                actual.ingresos_mxn AS ingresos_actual,
                previo.ingresos_mxn AS ingresos_anterior,
                actual.egresos_mxn AS egresos_actual,
                previo.egresos_mxn AS egresos_anterior,
                actual.num_cfdi_emitidos AS emitidos_actual,
                previo.num_cfdi_emitidos AS emitidos_anterior,
                actual.num_cfdi_recibidos AS recibidos_actual,
                previo.num_cfdi_recibidos AS recibidos_anterior,
                actual.ticket_promedio_emitido AS ticket_emitido_actual,
                previo.ticket_promedio_emitido AS ticket_emitido_anterior,
                actual.ticket_promedio_recibido AS ticket_recibido_actual,
                previo.ticket_promedio_recibido AS ticket_recibido_anterior
            FROM kpis_mensuales_empresa actual
            LEFT JOIN kpis_mensuales_empresa previo
                ON actual.rfc_empresa = previo.rfc_empresa
               AND previo.periodo = ?
            WHERE actual.periodo = ?
            {filtro_rfc}
            ORDER BY actual.rfc_empresa
            """,
            tuple([periodo_anterior, periodo_actual] + ([rfc_empresa.upper()] if rfc_empresa else [])),
        )

        for row in rows:
            row["variacion_ingresos_pct"] = _pct_change(row["ingresos_actual"], row["ingresos_anterior"])
            row["variacion_egresos_pct"] = _pct_change(row["egresos_actual"], row["egresos_anterior"])
            row["variacion_emitidos_pct"] = _pct_change(row["emitidos_actual"], row["emitidos_anterior"])
            row["variacion_recibidos_pct"] = _pct_change(row["recibidos_actual"], row["recibidos_anterior"])
            row["variacion_ticket_emitido_pct"] = _pct_change(
                row["ticket_emitido_actual"], row["ticket_emitido_anterior"]
            )
            row["variacion_ticket_recibido_pct"] = _pct_change(
                row["ticket_recibido_actual"], row["ticket_recibido_anterior"]
            )
        return rows
    finally:
        conn.close()


def _pct_change(actual: Any, anterior: Any) -> float | None:
    actual_num = float(actual or 0)
    anterior_num = float(anterior or 0)
    if anterior is None:
        return None
    if anterior_num == 0:
        return None if actual_num == 0 else 100.0
    return round(((actual_num - anterior_num) / anterior_num) * 100, 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Consultas rapidas de la capa analitica.")
    parser.add_argument("--query", required=True, choices=["kpis", "top", "variation"])
    parser.add_argument("--yyyy_mm", required=True, help="Periodo actual YYYY-MM")
    parser.add_argument("--previous-yyyy_mm", required=False, help="Periodo anterior YYYY-MM para variaciones")
    parser.add_argument("--rfc", required=False, help="RFC especifico")
    parser.add_argument("--rol", required=False, choices=["EMITIDA", "RECIBIDA"], help="Rol para query top")
    parser.add_argument("--top-n", type=int, default=10, help="Numero de registros para query top")
    parser.add_argument("--db-path", required=False, help="Ruta opcional a analytics.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH

    if args.query == "kpis":
        result = get_monthly_kpis(args.yyyy_mm, rfc_empresa=args.rfc, db_path=db_path)
    elif args.query == "top":
        if not args.rfc or not args.rol:
            raise SystemExit("--rfc y --rol son obligatorios para --query top")
        result = get_top_counterparties(args.yyyy_mm, args.rfc, args.rol, top_n=args.top_n, db_path=db_path)
    else:
        if not args.previous_yyyy_mm:
            raise SystemExit("--previous-yyyy_mm es obligatorio para --query variation")
        result = get_monthly_variation(
            periodo_actual=args.yyyy_mm,
            periodo_anterior=args.previous_yyyy_mm,
            rfc_empresa=args.rfc,
            db_path=db_path,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
