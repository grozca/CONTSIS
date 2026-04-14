from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
from runtime_paths import data_path

try:
    from src.analytics.insights import build_company_month_insights
    from src.analytics.schema import DB_PATH, get_connection
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.insights import build_company_month_insights
    from src.analytics.schema import DB_PATH, get_connection


DEFAULT_OUTPUT_DIR = data_path("bi_exports")


def export_bi_datasets(
    yyyy_mm: str | None = None,
    db_path: Path = DB_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    output_path = resolve_output_dir(output_dir, yyyy_mm)
    output_path.mkdir(parents=True, exist_ok=True)

    empresas_df = build_dim_empresas(db_path=db_path)
    periodos_df = build_dim_periodos(db_path=db_path, yyyy_mm=yyyy_mm)
    kpis_df = build_fact_kpis(db_path=db_path, yyyy_mm=yyyy_mm)
    variaciones_df = build_fact_variaciones(kpis_df)
    contrapartes_df = build_fact_contrapartes(db_path=db_path, yyyy_mm=yyyy_mm)
    riesgo_df = build_fact_riesgo(kpis_df, db_path=db_path)

    exports = {
        "dim_empresas.csv": empresas_df,
        "dim_periodos.csv": periodos_df,
        "fact_kpis_mensuales_empresa.csv": kpis_df,
        "fact_variaciones_mensuales.csv": variaciones_df,
        "fact_contrapartes_mensuales.csv": contrapartes_df,
        "fact_riesgo_mensual.csv": riesgo_df,
    }

    summary_exports: dict[str, int] = {}
    for filename, frame in exports.items():
        frame.to_csv(output_path / filename, index=False, encoding="utf-8-sig")
        summary_exports[filename] = len(frame)

    manifest = {
        "output_dir": str(output_path),
        "periodo_filtrado": yyyy_mm,
        "datasets": summary_exports,
    }
    (output_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def resolve_output_dir(output_dir: Path, yyyy_mm: str | None) -> Path:
    if yyyy_mm:
        return output_dir / yyyy_mm
    return output_dir / "all_periods"


def build_dim_empresas(db_path: Path = DB_PATH) -> pd.DataFrame:
    query = """
        SELECT
            rfc,
            razon_social,
            nombre_corto,
            activo,
            created_at
        FROM empresas
        ORDER BY COALESCE(nombre_corto, razon_social, rfc)
    """
    return read_sql(query, db_path=db_path)


def build_dim_periodos(db_path: Path = DB_PATH, yyyy_mm: str | None = None) -> pd.DataFrame:
    where_clause = "WHERE periodo = ?" if yyyy_mm else ""
    params: tuple[Any, ...] = (yyyy_mm,) if yyyy_mm else ()
    query = f"""
        SELECT DISTINCT periodo
        FROM kpis_mensuales_empresa
        {where_clause}
        ORDER BY periodo
    """
    frame = read_sql(query, params=params, db_path=db_path)
    if frame.empty:
        return pd.DataFrame(columns=["periodo", "anio", "mes", "fecha_periodo", "trimestre"])

    frame["anio"] = frame["periodo"].str.slice(0, 4).astype(int)
    frame["mes"] = frame["periodo"].str.slice(5, 7).astype(int)
    frame["fecha_periodo"] = pd.to_datetime(frame["periodo"] + "-01")
    frame["trimestre"] = "Q" + (((frame["mes"] - 1) // 3) + 1).astype(str)
    return frame


def build_fact_kpis(db_path: Path = DB_PATH, yyyy_mm: str | None = None) -> pd.DataFrame:
    where_clause = "WHERE k.periodo = ?" if yyyy_mm else ""
    params: tuple[Any, ...] = (yyyy_mm,) if yyyy_mm else ()
    query = f"""
        SELECT
            k.rfc_empresa,
            e.razon_social,
            e.nombre_corto,
            k.periodo,
            k.ingresos_mxn,
            k.egresos_mxn,
            (k.ingresos_mxn - k.egresos_mxn) AS balance_mxn,
            k.num_cfdi_emitidos,
            k.num_cfdi_recibidos,
            k.num_pagos,
            k.ticket_promedio_emitido,
            k.ticket_promedio_recibido,
            k.updated_at
        FROM kpis_mensuales_empresa k
        LEFT JOIN empresas e
            ON k.rfc_empresa = e.rfc
        {where_clause}
        ORDER BY k.periodo, k.rfc_empresa
    """
    return read_sql(query, params=params, db_path=db_path)


def build_fact_variaciones(kpis_df: pd.DataFrame) -> pd.DataFrame:
    if kpis_df.empty:
        return pd.DataFrame(
            columns=[
                "rfc_empresa",
                "periodo",
                "ingresos_anterior",
                "egresos_anterior",
                "emitidos_anterior",
                "recibidos_anterior",
                "pagos_anterior",
                "variacion_ingresos_pct",
                "variacion_egresos_pct",
                "variacion_emitidos_pct",
                "variacion_recibidos_pct",
                "variacion_pagos_pct",
            ]
        )

    frame = kpis_df.copy().sort_values(["rfc_empresa", "periodo"])
    group = frame.groupby("rfc_empresa", group_keys=False)

    frame["ingresos_anterior"] = group["ingresos_mxn"].shift(1)
    frame["egresos_anterior"] = group["egresos_mxn"].shift(1)
    frame["emitidos_anterior"] = group["num_cfdi_emitidos"].shift(1)
    frame["recibidos_anterior"] = group["num_cfdi_recibidos"].shift(1)
    frame["pagos_anterior"] = group["num_pagos"].shift(1)

    frame["variacion_ingresos_pct"] = pct_change_series(frame["ingresos_mxn"], frame["ingresos_anterior"])
    frame["variacion_egresos_pct"] = pct_change_series(frame["egresos_mxn"], frame["egresos_anterior"])
    frame["variacion_emitidos_pct"] = pct_change_series(frame["num_cfdi_emitidos"], frame["emitidos_anterior"])
    frame["variacion_recibidos_pct"] = pct_change_series(frame["num_cfdi_recibidos"], frame["recibidos_anterior"])
    frame["variacion_pagos_pct"] = pct_change_series(frame["num_pagos"], frame["pagos_anterior"])

    return frame[
        [
            "rfc_empresa",
            "periodo",
            "ingresos_anterior",
            "egresos_anterior",
            "emitidos_anterior",
            "recibidos_anterior",
            "pagos_anterior",
            "variacion_ingresos_pct",
            "variacion_egresos_pct",
            "variacion_emitidos_pct",
            "variacion_recibidos_pct",
            "variacion_pagos_pct",
        ]
    ]


def build_fact_contrapartes(db_path: Path = DB_PATH, yyyy_mm: str | None = None) -> pd.DataFrame:
    where_clause = "WHERE periodo = ?" if yyyy_mm else ""
    params: tuple[Any, ...] = (yyyy_mm,) if yyyy_mm else ()
    query = f"""
        SELECT
            rfc_empresa,
            periodo,
            rol,
            CASE
                WHEN rol = 'EMITIDA' THEN COALESCE(nombre_receptor, rfc_receptor, 'SIN_NOMBRE')
                ELSE COALESCE(nombre_emisor, rfc_emisor, 'SIN_NOMBRE')
            END AS nombre_counterparty,
            CASE
                WHEN rol = 'EMITIDA' THEN COALESCE(rfc_receptor, 'SIN_RFC')
                ELSE COALESCE(rfc_emisor, 'SIN_RFC')
            END AS rfc_counterparty,
            COUNT(*) AS num_cfdi,
            ROUND(COALESCE(SUM(total_mxn), 0), 2) AS monto_total_mxn
        FROM cfdi
        {where_clause}
        GROUP BY 1, 2, 3, 4, 5
        ORDER BY periodo, rfc_empresa, rol, monto_total_mxn DESC
    """
    frame = read_sql(query, params=params, db_path=db_path)
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "rfc_empresa",
                "periodo",
                "rol",
                "nombre_counterparty",
                "rfc_counterparty",
                "num_cfdi",
                "monto_total_mxn",
                "porcentaje_del_total",
                "rank_en_periodo",
            ]
        )

    totals = frame.groupby(["rfc_empresa", "periodo", "rol"])["monto_total_mxn"].transform("sum")
    frame["porcentaje_del_total"] = ((frame["monto_total_mxn"] / totals.fillna(0).replace(0, pd.NA)) * 100).round(2)
    frame["porcentaje_del_total"] = frame["porcentaje_del_total"].fillna(0.0)
    frame["rank_en_periodo"] = (
        frame.groupby(["rfc_empresa", "periodo", "rol"])["monto_total_mxn"]
        .rank(method="dense", ascending=False)
        .astype(int)
    )
    return frame


def build_fact_riesgo(kpis_df: pd.DataFrame, db_path: Path = DB_PATH) -> pd.DataFrame:
    columns = [
        "rfc_empresa",
        "periodo",
        "risk_score",
        "risk_level",
        "headline",
        "signal_count",
        "principal_signal",
        "top_cliente_pct",
        "top_proveedor_pct",
    ]
    if kpis_df.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for item in kpis_df[["rfc_empresa", "periodo"]].drop_duplicates().itertuples(index=False):
        insight = build_company_month_insights(item.periodo, item.rfc_empresa, db_path=db_path)
        risk = insight["risk"]
        top_clientes = insight["top_clientes"]
        top_proveedores = insight["top_proveedores"]

        rows.append(
            {
                "rfc_empresa": item.rfc_empresa,
                "periodo": item.periodo,
                "risk_score": risk["score"],
                "risk_level": risk["level"],
                "headline": risk["headline"],
                "signal_count": len(risk["signals"]),
                "principal_signal": risk["signals"][0]["message"] if risk["signals"] else None,
                "top_cliente_pct": top_clientes[0]["porcentaje_del_total"] if top_clientes else 0.0,
                "top_proveedor_pct": top_proveedores[0]["porcentaje_del_total"] if top_proveedores else 0.0,
            }
        )

    return pd.DataFrame(rows, columns=columns)


def pct_change_series(actual: pd.Series, previous: pd.Series) -> pd.Series:
    actual_num = pd.to_numeric(actual, errors="coerce").fillna(0)
    previous_num = pd.to_numeric(previous, errors="coerce")

    result = ((actual_num - previous_num) / previous_num) * 100
    result = result.round(2)

    result = result.mask(previous_num.isna())
    result = result.mask((previous_num == 0) & (actual_num == 0))
    result = result.mask((previous_num == 0) & (actual_num != 0), 100.0)
    return result


def read_sql(query: str, params: tuple[Any, ...] = (), db_path: Path = DB_PATH) -> pd.DataFrame:
    conn = get_connection(db_path)
    try:
        return pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta datasets curados para Power BI u otras herramientas BI.")
    parser.add_argument("--yyyy_mm", required=False, help="Filtra un periodo especifico YYYY-MM")
    parser.add_argument("--db-path", required=False, help="Ruta opcional a analytics.sqlite")
    parser.add_argument("--output-dir", required=False, help="Directorio base de salida para CSVs")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH
    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    manifest = export_bi_datasets(yyyy_mm=args.yyyy_mm, db_path=db_path, output_dir=output_dir)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
