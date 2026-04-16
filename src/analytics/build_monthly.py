from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

try:
    from src.analytics.kpis import compute_kpis_for_company_period, upsert_kpis
    from src.analytics.loader import build_company_period_context
    from src.analytics.schema import DB_PATH, create_tables, get_connection
    from src.analytics.transforms import transform_company_period_context
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.kpis import compute_kpis_for_company_period, upsert_kpis
    from src.analytics.loader import build_company_period_context
    from src.analytics.schema import DB_PATH, create_tables, get_connection
    from src.analytics.transforms import transform_company_period_context


def upsert_empresa(conn: sqlite3.Connection, context: dict[str, Any]) -> None:
    cliente = context.get("cliente")
    razon_social = context.get("razon_social")
    nombre_corto = context.get("nombre_corto")
    activo = 1 if context.get("activo", True) else 0

    conn.execute(
        """
        INSERT INTO empresas (rfc, razon_social, nombre_corto, activo)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(rfc) DO UPDATE SET
            razon_social = excluded.razon_social,
            nombre_corto = excluded.nombre_corto,
            activo = excluded.activo
        """,
        (
            context["rfc"],
            razon_social or (cliente.razon_social if cliente else None),
            nombre_corto or (cliente.nombre_corto if cliente else None),
            activo,
        ),
    )


def replace_cfdi_rows(
    conn: sqlite3.Connection,
    rfc_empresa: str,
    periodo: str,
    rows: list[dict[str, Any]],
) -> int:
    conn.execute(
        "DELETE FROM cfdi WHERE rfc_empresa = ? AND periodo = ?",
        (rfc_empresa, periodo),
    )
    if not rows:
        return 0

    conn.executemany(
        """
        INSERT INTO cfdi (
            uuid,
            rfc_empresa,
            periodo,
            rol,
            tipo_cfdi,
            fecha_emision,
            rfc_emisor,
            nombre_emisor,
            rfc_receptor,
            nombre_receptor,
            subtotal,
            descuento,
            total,
            moneda,
            tipo_cambio,
            total_mxn,
            metodo_pago,
            forma_pago,
            uso_cfdi,
            estatus_cancelado,
            source_file
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(uuid) DO UPDATE SET
            rfc_empresa = excluded.rfc_empresa,
            periodo = excluded.periodo,
            rol = excluded.rol,
            tipo_cfdi = excluded.tipo_cfdi,
            fecha_emision = excluded.fecha_emision,
            rfc_emisor = excluded.rfc_emisor,
            nombre_emisor = excluded.nombre_emisor,
            rfc_receptor = excluded.rfc_receptor,
            nombre_receptor = excluded.nombre_receptor,
            subtotal = excluded.subtotal,
            descuento = excluded.descuento,
            total = excluded.total,
            moneda = excluded.moneda,
            tipo_cambio = excluded.tipo_cambio,
            total_mxn = excluded.total_mxn,
            metodo_pago = excluded.metodo_pago,
            forma_pago = excluded.forma_pago,
            uso_cfdi = excluded.uso_cfdi,
            estatus_cancelado = excluded.estatus_cancelado,
            source_file = excluded.source_file,
            ingested_at = CURRENT_TIMESTAMP
        """,
        [
            (
                row["uuid"],
                row["rfc_empresa"],
                row["periodo"],
                row["rol"],
                row["tipo_cfdi"],
                row["fecha_emision"],
                row["rfc_emisor"],
                row["nombre_emisor"],
                row["rfc_receptor"],
                row["nombre_receptor"],
                row["subtotal"],
                row["descuento"],
                row["total"],
                row["moneda"],
                row["tipo_cambio"],
                row["total_mxn"],
                row["metodo_pago"],
                row["forma_pago"],
                row["uso_cfdi"],
                row["estatus_cancelado"],
                row["source_file"],
            )
            for row in rows
        ],
    )
    return len(rows)


def replace_pagos_rows(conn: sqlite3.Connection, rfc_empresa: str, periodo: str, rows: list[dict[str, Any]]) -> int:
    conn.execute("DELETE FROM pagos WHERE rfc_empresa = ? AND periodo = ?", (rfc_empresa, periodo))
    if not rows:
        return 0

    conn.executemany(
        """
        INSERT INTO pagos (
            uuid_pago,
            uuid_factura_relacionada,
            rfc_empresa,
            periodo,
            fecha_pago,
            monto_pago,
            moneda,
            tipo_cambio,
            monto_pago_mxn,
            rfc_emisor_pago,
            rfc_receptor_pago
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                row["uuid_pago"],
                row["uuid_factura_relacionada"],
                row["rfc_empresa"],
                row["periodo"],
                row["fecha_pago"],
                row["monto_pago"],
                row["moneda"],
                row["tipo_cambio"],
                row["monto_pago_mxn"],
                row["rfc_emisor_pago"],
                row["rfc_receptor_pago"],
            )
            for row in rows
        ],
    )
    return len(rows)


def build_monthly(periodo: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    contexts = build_company_period_context(periodo)
    conn = get_connection(db_path)
    create_tables(conn)

    summary = {
        "periodo": periodo,
        "empresas_detectadas": len(contexts),
        "empresas_procesadas": 0,
        "cfdi_rows": 0,
        "pagos_rows": 0,
        "kpis_rows": 0,
    }

    try:
        for context in contexts:
            result = transform_company_period_context(context)

            upsert_empresa(conn, context)
            summary["cfdi_rows"] += replace_cfdi_rows(
                conn,
                context["rfc"],
                context["periodo"],
                result.cfdi_rows,
            )
            summary["pagos_rows"] += replace_pagos_rows(
                conn,
                context["rfc"],
                context["periodo"],
                result.pagos_rows,
            )

            kpi_row = compute_kpis_for_company_period(
                cfdi_rows=result.cfdi_rows,
                pagos_rows=result.pagos_rows,
                rfc_empresa=context["rfc"],
                periodo=context["periodo"],
            )
            upsert_kpis(conn, kpi_row)

            summary["kpis_rows"] += 1
            summary["empresas_procesadas"] += 1

        conn.commit()
    finally:
        conn.close()

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye la capa analitica mensual para un periodo.")
    parser.add_argument("--yyyy_mm", required=True, help="Periodo a procesar en formato YYYY-MM")
    parser.add_argument("--db-path", required=False, help="Ruta opcional de la base analytics.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH
    summary = build_monthly(args.yyyy_mm, db_path=db_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
