from __future__ import annotations

import base64
import getpass
import io
import json
import os
import sqlite3
import socket
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from runtime_paths import asset_path, data_path, load_project_env, merged_dotenv_values, preferred_env_path

load_project_env()

try:
    from src.analytics.alert_payloads import build_alert_payload
    from src.analytics.bi_exports import export_bi_datasets
    from src.analytics.build_monthly import build_monthly
    from src.analytics.dashboard_queries import (
        get_dashboard_dataset,
        list_available_periods,
        list_available_years,
    )
    from src.analytics.loader import load_clientes
    from src.app.pilot_preferences import get_company_account_owner
    from src.analytics.schema import DB_PATH, initialize_database
    from src.utils.config import settings
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.alert_payloads import build_alert_payload
    from src.analytics.bi_exports import export_bi_datasets
    from src.analytics.build_monthly import build_monthly
    from src.analytics.dashboard_queries import (
        get_dashboard_dataset,
        list_available_periods,
        list_available_years,
    )
    from src.analytics.loader import load_clientes
    from src.app.pilot_preferences import get_company_account_owner
    from src.analytics.schema import DB_PATH, initialize_database
    from src.utils.config import settings


REPORTS_DIR = data_path("reportes_app")
LOGO_PATH = asset_path("src", "assets", "logo_sisrodriguez_transparente.png")
ALERT_LOGO_PATH = asset_path("src", "assets", "logo_sisrodriguez_isotipo.png")
EXECUTION_LOG_PATH = data_path("app_logs", "operation_history.jsonl")
EXPORTS_DIR = data_path("exports")
BI_EXPORTS_DIR = data_path("bi_exports")
ALERTS_ENV_PATH = preferred_env_path()


@dataclass
class ActionResult:
    success: bool
    title: str
    message: str
    artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def _zip_dir() -> Path:
    return Path(settings.boveda_dir) / "zip"


def _extract_dir() -> Path:
    return Path(settings.boveda_dir) / "extract"


def _organized_dir() -> Path:
    return Path(settings.organized_dir)


def ensure_analytics_database() -> None:
    initialize_database()


def get_company_options() -> list[dict[str, Any]]:
    clientes = load_clientes()
    companies: list[dict[str, Any]] = []

    for rfc, cliente in clientes.items():
        raw = cliente.raw or {}
        nombre = cliente.nombre_corto or cliente.razon_social or rfc
        companies.append(
            {
                "rfc": rfc,
                "nombre": nombre,
                "razon_social": cliente.razon_social,
                "nombre_corto": cliente.nombre_corto,
                "emails": list(raw.get("emails") or []),
                "es_despacho": bool(raw.get("es_despacho", False)),
                "dueno_cuenta": get_company_account_owner(raw),
                "raw": raw,
            }
        )

    return sorted(
        companies,
        key=lambda item: (
            0 if item.get("es_despacho") else 1,
            str(item.get("nombre") or item.get("rfc") or "").upper(),
        ),
    )


def get_period_options(rfc_empresa: str | None = None) -> list[str]:
    ensure_analytics_database()
    analytics_periods = sorted(set(list_available_periods(rfc_empresa)), reverse=True)
    extract_periods = _discover_extract_periods(rfc_empresa) if rfc_empresa else []
    ordered_periods: list[str] = []
    seen: set[str] = set()

    for period in extract_periods:
        if period not in seen:
            ordered_periods.append(period)
            seen.add(period)

    for period in analytics_periods:
        if period not in seen:
            ordered_periods.append(period)
            seen.add(period)

    return ordered_periods


def get_year_options(rfc_empresa: str | None = None) -> list[int]:
    periods = get_period_options(rfc_empresa)
    if periods:
        return sorted({int(period[:4]) for period in periods}, reverse=True)
    return list_available_years(rfc_empresa)


def _discover_extract_periods(rfc_empresa: str | None) -> list[str]:
    if not rfc_empresa:
        return []

    rfc_dir = _extract_dir() / rfc_empresa.upper()
    if not rfc_dir.exists():
        return []

    periods: set[str] = set()

    # Estructura A: <RFC>/<YYYY>/<MM>/<ROL>
    for year_dir in (path for path in rfc_dir.iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 4):
        for month_dir in (path for path in year_dir.iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 2):
            periods.add(f"{year_dir.name}-{month_dir.name}")

    # Estructura B: <RFC>/<ROL>/<YYYY>/<MM>
    for role_dir in (path for path in rfc_dir.iterdir() if path.is_dir()):
        for year_dir in (path for path in role_dir.iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 4):
            for month_dir in (path for path in year_dir.iterdir() if path.is_dir() and path.name.isdigit() and len(path.name) == 2):
                periods.add(f"{year_dir.name}-{month_dir.name}")

    return sorted(periods, reverse=True)


def get_dashboard_context(
    periodo: str,
    rfc_empresa: str,
    analysis_mode: str = "monthly",
    year: int | None = None,
    month_cutoff: int | None = None,
) -> dict[str, Any]:
    ensure_analytics_database()
    dataset = get_dashboard_dataset(
        periodo,
        rfc_empresa,
        analysis_mode=analysis_mode,
        year=year,
        month_cutoff=month_cutoff,
    )
    if analysis_mode.lower() == "monthly":
        raw_frames = _load_monthly_cfdi_frames(periodo, rfc_empresa)
        dataset.update(raw_frames)
        dataset.setdefault("insights", {}).update(raw_frames)
    return dataset


def build_analytics_for_period(periodo: str) -> ActionResult:
    try:
        ensure_analytics_database()
        summary = build_monthly(periodo)
        result = ActionResult(
            success=True,
            title="Analytics construidos",
            message=f"Se actualizaron los indicadores, tablas y datos del dashboard para {periodo}.",
            details=summary,
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error al construir analytics",
            message=f"No se pudieron construir analytics para {periodo}: {exc}",
            details={"periodo": periodo, "error": str(exc)},
        )
    _log_action("build_analytics", None, periodo, result)
    return result


def export_bi_for_period(periodo: str | None = None) -> ActionResult:
    try:
        manifest = export_bi_datasets(yyyy_mm=periodo)
        result = ActionResult(
            success=True,
            title="Datasets BI exportados",
            message="Los CSVs para Power BI quedaron listos para conectar o compartir.",
            artifacts=[manifest["output_dir"]],
            details=manifest,
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error al exportar BI",
            message=f"No se pudieron exportar los datasets BI: {exc}",
            details={"periodo": periodo, "error": str(exc)},
        )
    _log_action("export_bi", None, periodo, result)
    return result


def preview_alert_payload(periodo: str, rfc_empresa: str) -> dict[str, Any]:
    return build_alert_payload(periodo=periodo, rfc_empresa=rfc_empresa)


def preview_company_alert_email(periodo: str, rfc_empresa: str) -> dict[str, Any]:
    runtime = _load_alertas_runtime()
    cfg = runtime["validar_config"](runtime["cargar_config"]()).raw
    clientes = runtime["cargar_clientes"]()
    logger = runtime["setup_logging"]()

    rfc = rfc_empresa.upper()
    datos = runtime["cargar_datos_cliente_periodo"](rfc, periodo, logger)
    if not datos.tiene_e and not datos.tiene_r:
        raise FileNotFoundError(f"No se encontraron Excel para {rfc} en {periodo}.")

    alertas_cliente = runtime["evaluar_cliente_periodo"](datos, cfg, clientes, logger)
    nombre = runtime["nombre_cliente"](rfc, clientes)
    year, month = periodo.split("-")
    mes_label = runtime["MESES_ES"].get(int(month), month).capitalize()
    subject = f"Reporte Mensual CFDI - {nombre} - {mes_label} {year}"
    html = runtime["render_html_cliente"](rfc, periodo, alertas_cliente, datos, clientes)

    stats_emitidas = _summarize_alert_frame(datos.df_e)
    stats_recibidas = _summarize_alert_frame(datos.df_r)
    severidad = _summarize_alert_levels(alertas_cliente)
    regimen_insight = runtime["build_regimen_insight"](datos)
    text = _build_client_alert_text(
        nombre=nombre,
        rfc=rfc,
        periodo=periodo,
        stats_emitidas=stats_emitidas,
        stats_recibidas=stats_recibidas,
        regimen_insight=regimen_insight,
        alertas=alertas_cliente,
    )
    pdf_bytes: bytes | None = None
    pdf_error: str | None = None
    try:
        pdf_bytes = _build_alert_pdf(
            subject=subject,
            company_name=nombre,
            rfc=rfc,
            periodo=periodo,
            stats_emitidas=stats_emitidas,
            stats_recibidas=stats_recibidas,
            regimen_insight=regimen_insight,
            severity_summary=severidad,
            alerts=alertas_cliente,
        )
    except Exception as exc:
        pdf_error = str(exc)

    return {
        "subject": subject,
        "html": html,
        "text": text,
        "pdf_bytes": pdf_bytes,
        "pdf_error": pdf_error,
        "empresa": {"rfc": rfc, "nombre": nombre},
        "regimen": regimen_insight,
        "summary": {
            "num_cfdi_emitidos": stats_emitidas["count"],
            "num_cfdi_recibidos": stats_recibidas["count"],
            "ingresos_mxn": stats_emitidas["total"],
            "egresos_mxn": stats_recibidas["total"],
            "alert_total": severidad["total"],
            "alta": severidad["alta"],
            "media": severidad["media"],
            "baja": severidad["baja"],
            "tiene_emitidas": bool(datos.tiene_e),
            "tiene_recibidas": bool(datos.tiene_r),
        },
        "alerts": [
            {
                "severity": alerta.severidad,
                "type": alerta.tipo_alerta,
                "summary": alerta.resumen,
                "detail": alerta.detalle,
                "amount": float(alerta.monto_total or 0),
                "count": int(alerta.cantidad or 0),
            }
            for alerta in alertas_cliente
        ],
    }


def generate_client_report(periodo: str, rfc_empresa: str, output_dir: Path = REPORTS_DIR) -> ActionResult:
    try:
        payload = build_alert_payload(periodo=periodo, rfc_empresa=rfc_empresa)
        report_html = build_branded_report_html(payload)
        report_text = payload["text"]

        period_dir = output_dir / periodo
        period_dir.mkdir(parents=True, exist_ok=True)
        safe_rfc = rfc_empresa.upper()
        html_path = period_dir / f"{safe_rfc}_reporte_ejecutivo.html"
        txt_path = period_dir / f"{safe_rfc}_reporte_ejecutivo.txt"
        html_path.write_text(report_html, encoding="utf-8")
        txt_path.write_text(report_text, encoding="utf-8")

        result = ActionResult(
            success=True,
            title="Reporte generado",
            message=f"Se preparo el reporte ejecutivo de {safe_rfc} para {periodo}.",
            artifacts=[str(html_path), str(txt_path)],
            details={
                "subject": payload["subject"],
                "html": report_html,
                "text": report_text,
                "output_html": str(html_path),
                "output_text": str(txt_path),
            },
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error al generar reporte",
            message=f"No se pudo generar el reporte ejecutivo: {exc}",
            details={"rfc": rfc_empresa, "periodo": periodo, "error": str(exc)},
        )
    _log_action("generate_report", rfc_empresa.upper(), periodo, result)
    return result


def run_operational_pipeline(rfc_empresa: str, year: int, month: int) -> ActionResult:
    import main as project_main

    periodo = f"{year:04d}-{month:02d}"
    try:
        project_main._run_pipeline(rfc_empresa.upper(), year, month)
        result = ActionResult(
            success=True,
            title="Pipeline CFDI ejecutado",
            message=f"Se corrieron los bots base para {rfc_empresa.upper()} en {periodo}.",
            details={"rfc": rfc_empresa.upper(), "year": year, "month": month},
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error en pipeline CFDI",
            message=f"No se pudo completar el pipeline base: {exc}",
            details={"rfc": rfc_empresa.upper(), "year": year, "month": month, "error": str(exc)},
        )
    _log_action("pipeline_base", rfc_empresa.upper(), periodo, result)
    return result


def run_operational_step(step: str, rfc_empresa: str | None = None, year: int | None = None, month: int | None = None) -> ActionResult:
    step = step.lower()
    periodo = f"{year:04d}-{month:02d}" if year and month else None

    try:
        if step == "r6":
            from src.robots import bot_descomprimir

            bot_descomprimir.run()
            result = ActionResult(True, "R6 completado", f"Se descomprimieron los ZIPs y se enruto XML hacia {_extract_dir()}.")
        elif step == "r6fix":
            from src.robots import bot_fix_reorganizar

            bot_fix_reorganizar.run()
            result = ActionResult(True, "R6fix completado", "Se corrigio la organizacion interna de XML ya extraidos.")
        elif step in {"r7", "r7a"}:
            from src.robots import bot_cargar_xml_a_bd_min

            bot_cargar_xml_a_bd_min.main()
            result = ActionResult(
                True,
                "R7 completado",
                f"Se cargaron XML a la base operativa {settings.db_path}.",
                artifacts=[str(settings.db_path)],
            )
        elif step == "r8":
            if not (rfc_empresa and year and month):
                raise ValueError("R8 requiere RFC, anio y mes.")
            _run_robot_main(
                "bot_export_excel",
                ["r8", "--rfc", rfc_empresa.upper(), "--year", str(year), "--month", str(month), "--roles", "RECIBIDAS,EMITIDAS"],
            )
            artifacts = [str(path) for path in discover_generated_files(rfc_empresa, periodo)["excel_files"]]
            if artifacts:
                try:
                    analytics_summary = build_monthly(periodo)
                except Exception as analytics_exc:
                    result = ActionResult(
                        False,
                        "R8 parcial",
                        "Los Excel del periodo se generaron, pero fallo la actualizacion de analytics para el dashboard.",
                        artifacts=artifacts,
                        details={
                            "rfc": rfc_empresa.upper(),
                            "periodo": periodo,
                            "error": str(analytics_exc),
                        },
                    )
                else:
                    result = ActionResult(
                        True,
                        "R8 completado",
                        "El Excel SAT del periodo ya quedo listo y la capa analitica se actualizo para el dashboard.",
                        artifacts=artifacts,
                        details={
                            "rfc": rfc_empresa.upper(),
                            "periodo": periodo,
                            "analytics_summary": analytics_summary,
                        },
                    )
            else:
                result = ActionResult(
                    False,
                    "R8 sin archivos",
                    f"No se generaron Excels para {rfc_empresa.upper()} en {periodo}. Revisa que existan XML en {_extract_dir()} para ese RFC y periodo.",
                    details={"rfc": rfc_empresa.upper(), "periodo": periodo},
                )
        elif step == "r9":
            if not (rfc_empresa and year and month):
                raise ValueError("R9 requiere RFC, anio y mes.")
            _run_robot_main("bot_export_resumen", ["r9", "--rfc", rfc_empresa.upper(), "--yyyy_mm", periodo])
            artifacts = [str(path) for path in discover_generated_files(rfc_empresa, periodo)["word_files"]]
            if artifacts:
                result = ActionResult(True, "R9 completado", "El resumen Word del periodo ya quedo listo.", artifacts=artifacts)
            else:
                result = ActionResult(
                    False,
                    "R9 sin archivos",
                    f"No se genero el resumen Word para {rfc_empresa.upper()} en {periodo}.",
                    details={"rfc": rfc_empresa.upper(), "periodo": periodo},
                )
        else:
            raise ValueError(f"Paso desconocido: {step}")
    except Exception as exc:
        result = ActionResult(
            success=False,
            title=f"Error en {step.upper()}",
            message=f"No se pudo ejecutar {step.upper()}: {exc}",
            details={"step": step, "error": str(exc), "rfc": rfc_empresa, "periodo": periodo},
        )

    _log_action(step, rfc_empresa.upper() if rfc_empresa else None, periodo, result)
    return result


def run_alerts(periodo: str, piloto: bool = True, forzar: bool = False) -> ActionResult:
    import src.cli as project_cli

    action = "alertas_piloto" if piloto else ("alertas_forzadas" if forzar else "alertas_envio")
    try:
        project_cli._run_alertas(periodo, piloto=piloto, forzar=forzar)
        modo = "piloto" if piloto else "envio real"
        sufijo = " (forzado)" if forzar and not piloto else ""
        result = ActionResult(
            success=True,
            title="Alertas ejecutadas",
            message=f"Se ejecutaron alertas en modo {modo}{sufijo} para {periodo}.",
            details={"periodo": periodo, "piloto": piloto, "forzar": forzar},
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error al ejecutar alertas",
            message=f"No se pudieron ejecutar las alertas para {periodo}: {exc}",
            details={"periodo": periodo, "piloto": piloto, "forzar": forzar, "error": str(exc)},
        )
    _log_action(action, None, periodo, result)
    return result


def run_company_alert(periodo: str, rfc_empresa: str, piloto: bool = True, forzar: bool = False) -> ActionResult:
    action = "alertas_empresa_piloto" if piloto else ("alertas_empresa_forzadas" if forzar else "alertas_empresa_envio")
    try:
        runtime = _load_alertas_runtime()
        cfg = runtime["validar_config"](runtime["cargar_config"]()).raw
        clientes = runtime["cargar_clientes"]()
        historial = runtime["HistorialAlertasRepository"]()
        historial.init_db()
        runtime["ejecutar_modo_cliente"](rfc_empresa.upper(), periodo, cfg, clientes, piloto, forzar, historial)

        modo = "piloto" if piloto else "envio real al director"
        sufijo = " (forzado)" if forzar and not piloto else ""
        result = ActionResult(
            success=True,
            title="Alerta por empresa ejecutada",
            message=f"Se ejecuto la alerta de {rfc_empresa.upper()} en modo {modo}{sufijo} para {periodo}.",
            details={"periodo": periodo, "rfc": rfc_empresa.upper(), "piloto": piloto, "forzar": forzar},
        )
    except Exception as exc:
        result = ActionResult(
            success=False,
            title="Error al ejecutar alerta por empresa",
            message=f"No se pudo ejecutar la alerta de {rfc_empresa.upper()} para {periodo}: {exc}",
            details={"periodo": periodo, "rfc": rfc_empresa.upper(), "piloto": piloto, "forzar": forzar, "error": str(exc)},
        )
    _log_action(action, rfc_empresa.upper(), periodo, result)
    return result


def get_operational_status(rfc_empresa: str | None, periodo: str) -> dict[str, Any]:
    year, month = _parse_period(periodo)
    y = f"{year:04d}"
    m = f"{month:02d}"

    extract_root = _extract_dir()
    extracted_total_files = list(extract_root.rglob("*.xml")) if extract_root.exists() else []
    extracted_global_period_files = list(extract_root.glob(f"**/{y}/{m}/*.xml")) if extract_root.exists() else []
    extracted_files = []
    extracted_period_files = extracted_global_period_files
    if rfc_empresa:
        rfc = rfc_empresa.upper()
        rfc_extract = extract_root / rfc
        if rfc_extract.exists():
            extracted_files = list(rfc_extract.rglob("*.xml"))
            extracted_period_files = list(rfc_extract.glob(f"**/{y}/{m}/*.xml"))

    generated = discover_generated_files(rfc_empresa, periodo) if rfc_empresa else {
        "excel_files": [],
        "word_files": [],
        "report_files": [],
        "alert_files": [],
        "bi_files": [],
    }

    analytics_db = DB_PATH
    operational_db = Path(settings.db_path)
    zip_root = _zip_dir()
    zip_count = len(list(zip_root.glob("*.zip"))) if zip_root.exists() else 0
    operational_cfdi_count = _count_operational_cfdi_rows(operational_db, rfc_empresa, periodo)
    analytics_kpi_count = _count_analytics_kpis_rows(analytics_db, rfc_empresa, periodo)

    checks = [
        _check("RFC seleccionado", bool(rfc_empresa), "Empresa activa seleccionada en la barra lateral."),
        _check("ZIPs encontrados", zip_count > 0, f"{zip_count} archivo(s) ZIP detectados en {_zip_dir()}."),
        _check("XML extraidos totales", len(extracted_total_files) > 0, f"{len(extracted_total_files)} XML detectados en {_extract_dir()}."),
        _check(
            "XML del RFC activo",
            len(extracted_files) > 0 if rfc_empresa else len(extracted_total_files) > 0,
            f"{len(extracted_files) if rfc_empresa else len(extracted_total_files)} XML detectados para consulta operativa.",
        ),
        _check("XML del periodo en extract", len(extracted_period_files) > 0, f"{len(extracted_period_files)} XML detectados en {periodo}."),
        _check(
            "Base operativa CFDI",
            operational_cfdi_count > 0,
            f"{operational_cfdi_count} CFDI detectados en {operational_db} para {rfc_empresa or 'el periodo'} {periodo}.",
        ),
        _check("Excel SAT generado", len(generated["excel_files"]) > 0, f"{len(generated['excel_files'])} archivo(s) Excel para el periodo."),
        _check("Resumen Word generado", len(generated["word_files"]) > 0, f"{len(generated['word_files'])} archivo(s) Word para el periodo."),
        _check(
            "Analytics construidos",
            analytics_kpi_count > 0,
            f"{analytics_kpi_count} fila(s) KPI detectadas en {analytics_db} para {rfc_empresa or 'el periodo'} {periodo}.",
        ),
        _check("Reporte despacho generado", len(generated["report_files"]) > 0, f"{len(generated['report_files'])} reporte(s) generados para el periodo."),
        _check("Export BI del periodo", len(generated["bi_files"]) > 0, f"{len(generated['bi_files'])} archivo(s) BI en carpeta del periodo."),
    ]

    return {
        "rfc": rfc_empresa,
        "periodo": periodo,
        "checks": checks,
        "artifacts": generated,
        "summary": {
            "zip_files": zip_count,
            "extract_count": len(extracted_total_files),
            "extract_period_count": len(extracted_period_files),
            "db_ready": int(operational_cfdi_count > 0),
            "analytics_ready": int(analytics_kpi_count > 0),
            "excel_count": len(generated["excel_files"]),
            "word_count": len(generated["word_files"]),
            "report_count": len(generated["report_files"]),
        },
    }


def discover_generated_files(rfc_empresa: str | None, periodo: str) -> dict[str, list[Path]]:
    if not rfc_empresa:
        return {"excel_files": [], "word_files": [], "report_files": [], "alert_files": [], "bi_files": []}

    rfc = rfc_empresa.upper()
    export_dir = EXPORTS_DIR / rfc / periodo
    report_dir = REPORTS_DIR / periodo
    bi_dir = BI_EXPORTS_DIR / periodo

    excel_files = _clean_file_list(export_dir.glob("*.xlsx")) if export_dir.exists() else []
    word_files = _clean_file_list(export_dir.glob("*.docx")) if export_dir.exists() else []
    report_files = _clean_file_list(report_dir.glob(f"{rfc}_*")) if report_dir.exists() else []
    bi_files = _clean_file_list(bi_dir.glob("*.csv")) if bi_dir.exists() else []
    alert_files: list[Path] = []
    return {
        "excel_files": excel_files,
        "word_files": word_files,
        "report_files": report_files,
        "alert_files": alert_files,
        "bi_files": bi_files,
    }


def get_recent_execution_log(limit: int = 20) -> list[dict[str, Any]]:
    if not EXECUTION_LOG_PATH.exists():
        return []
    entries = []
    for line in EXECUTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return list(reversed(entries[-limit:]))


def get_mail_configuration_status() -> dict[str, Any]:
    values = merged_dotenv_values()
    remitente = (values.get("EMAIL_REMITENTE") or "").strip()
    destinatarios_raw = (values.get("EMAIL_DESTINATARIOS") or "").strip()
    password = (values.get("EMAIL_PASSWORD") or "").strip()
    destinatarios = [item.strip() for item in destinatarios_raw.split(",") if item.strip()]

    return {
        "env_path": str(ALERTS_ENV_PATH),
        "configured": bool(remitente and password and destinatarios),
        "sender": remitente or None,
        "recipient_count": len(destinatarios),
        "has_password": bool(password),
        "has_recipients": bool(destinatarios),
    }


def build_branded_report_html(payload: dict[str, Any]) -> str:
    insight = payload["insight"]
    empresa = insight["empresa"]
    kpis = insight["kpis"]
    risk = insight["risk"]
    variation = insight["variation"]
    logo_data = get_logo_data_uri()

    top_clientes_html = "".join(_top_row(row) for row in payload["insight"].get("top_clientes", [])) or _empty_row()
    top_proveedores_html = "".join(_top_row(row) for row in payload["insight"].get("top_proveedores", [])) or _empty_row()
    signal_items = "".join(
        f"<li><strong>{signal['severity'].upper()}</strong>: {signal['message']}</li>"
        for signal in risk.get("signals", [])
    ) or "<li>Sin alertas relevantes</li>"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{payload['subject']}</title>
  <style>
    body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f4f7fb; color: #122033; margin: 0; padding: 32px; }}
    .sheet {{ max-width: 1080px; margin: 0 auto; background: white; border-radius: 24px; overflow: hidden; box-shadow: 0 26px 60px rgba(18, 32, 51, 0.12); }}
    .hero {{ background: linear-gradient(135deg, #102542 0%, #1f6e8c 100%); color: #f8fafc; padding: 28px 34px; }}
    .hero-top {{ display: flex; justify-content: space-between; align-items: center; gap: 18px; }}
    .logo {{ max-height: 64px; max-width: 220px; object-fit: contain; background: rgba(255,255,255,0.08); border-radius: 14px; padding: 8px 12px; }}
    .hero h1 {{ margin: 14px 0 8px; font-size: 2rem; }}
    .hero p {{ margin: 0.25rem 0; opacity: 0.92; }}
    .hero-badges span {{ display: inline-block; margin-right: 10px; margin-top: 10px; background: rgba(255,255,255,0.12); border: 1px solid rgba(255,255,255,0.16); border-radius: 999px; padding: 8px 12px; font-size: 0.92rem; }}
    .section {{ padding: 24px 34px; }}
    .section h2 {{ margin: 0 0 14px; font-size: 1.15rem; color: #102542; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(220px, 1fr)); gap: 14px; }}
    .card {{ background: #f8fafc; border: 1px solid #e6edf5; border-radius: 18px; padding: 16px; }}
    .label {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.75rem; color: #607081; margin-bottom: 8px; }}
    .value {{ font-size: 1.4rem; font-weight: 700; color: #102542; }}
    .subtle {{ color: #607081; font-size: 0.92rem; margin-top: 6px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
    th, td {{ text-align: left; padding: 10px 8px; border-bottom: 1px solid #e6edf5; font-size: 0.95rem; }}
    th {{ background: #f8fafc; color: #37516a; }}
    ul {{ padding-left: 18px; margin: 10px 0 0; }}
  </style>
</head>
<body>
  <div class="sheet">
    <div class="hero">
      <div class="hero-top">
        <div>
          <div style="text-transform: uppercase; letter-spacing: 0.14em; font-size: 0.78rem; opacity: 0.76;">Despacho</div>
          <h1>Reporte Ejecutivo CFDI</h1>
          <p>{empresa.get('nombre_corto') or empresa.get('rfc')}</p>
          <p>RFC: {empresa.get('rfc')} | Periodo: {payload['metadata']['periodo']}</p>
        </div>
        {f'<img class="logo" src="{logo_data}" alt="Logo despacho">' if logo_data else ''}
      </div>
      <div class="hero-badges">
        <span>Riesgo: {risk['level'].upper()} ({risk['score']})</span>
        <span>{risk['headline']}</span>
      </div>
    </div>

    <div class="section">
      <h2>Resumen del periodo</h2>
      <div class="grid">
        <div class="card"><div class="label">Ingresos</div><div class="value">{_fmt_currency(kpis['ingresos_mxn'])}</div><div class="subtle">Variacion: {_fmt_pct_or_na(variation.get('variacion_ingresos_pct'))}</div></div>
        <div class="card"><div class="label">Egresos</div><div class="value">{_fmt_currency(kpis['egresos_mxn'])}</div><div class="subtle">Variacion: {_fmt_pct_or_na(variation.get('variacion_egresos_pct'))}</div></div>
        <div class="card"><div class="label">Resultado</div><div class="value">{_fmt_currency(float(kpis['ingresos_mxn']) - float(kpis['egresos_mxn']))}</div><div class="subtle">Balance entre ingresos y egresos del periodo</div></div>
        <div class="card"><div class="label">CFDI emitidos</div><div class="value">{kpis['num_cfdi_emitidos']}</div><div class="subtle">Ticket promedio: {_fmt_currency(kpis['ticket_promedio_emitido'])}</div></div>
        <div class="card"><div class="label">CFDI recibidos</div><div class="value">{kpis['num_cfdi_recibidos']}</div><div class="subtle">Ticket promedio: {_fmt_currency(kpis['ticket_promedio_recibido'])}</div></div>
        <div class="card"><div class="label">Complementos de pago</div><div class="value">{kpis['num_pagos']}</div><div class="subtle">Actividad operativa del periodo</div></div>
      </div>
    </div>

    <div class="section"><h2>Senales ejecutivas</h2><ul>{signal_items}</ul></div>
    <div class="section"><h2>Top clientes</h2><table><thead><tr><th>Nombre</th><th>RFC</th><th>CFDI</th><th>Monto</th><th>% del total</th></tr></thead><tbody>{top_clientes_html}</tbody></table></div>
    <div class="section"><h2>Top proveedores</h2><table><thead><tr><th>Nombre</th><th>RFC</th><th>CFDI</th><th>Monto</th><th>% del total</th></tr></thead><tbody>{top_proveedores_html}</tbody></table></div>
  </div>
</body>
</html>
"""


def get_logo_data_uri() -> str | None:
    if not LOGO_PATH.exists():
        return None
    encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def default_period() -> str:
    return datetime.now().strftime("%Y-%m")


def _run_robot_main(modulo: str, argv: list[str]) -> None:
    mod = __import__(f"src.robots.{modulo}", fromlist=["main"])
    original_argv = sys.argv[:]
    try:
        sys.argv = argv
        mod.main()
    finally:
        sys.argv = original_argv


def _log_action(action: str, rfc: str | None, periodo: str | None, result: ActionResult) -> None:
    EXECUTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "rfc": rfc,
        "periodo": periodo,
        "success": result.success,
        "title": result.title,
        "message": result.message,
        "artifacts": result.artifacts,
        "user": _current_user(),
        "host": socket.gethostname(),
    }
    with EXECUTION_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + os.linesep)


def _current_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "desconocido"


def _parse_period(periodo: str) -> tuple[int, int]:
    year_str, month_str = periodo.split("-")
    return int(year_str), int(month_str)


def _check(label: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"label": label, "ok": ok, "detail": detail}


def _sqlite_scalar(db_path: Path, query: str, params: tuple[Any, ...] = ()) -> Any:
    if not db_path.exists():
        return None

    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(db_path)
        row = con.execute(query, params).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        if con is not None:
            con.close()


def _sqlite_table_exists(db_path: Path, table_name: str) -> bool:
    value = _sqlite_scalar(
        db_path,
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return bool(value)


def _count_operational_cfdi_rows(db_path: Path, rfc_empresa: str | None, periodo: str) -> int:
    if not _sqlite_table_exists(db_path, "cfdi"):
        return 0

    if rfc_empresa:
        value = _sqlite_scalar(
            db_path,
            """
            SELECT COUNT(*)
            FROM cfdi
            WHERE substr(COALESCE(fecha, ''), 1, 7) = ?
              AND (UPPER(COALESCE(emisor_rfc, '')) = ? OR UPPER(COALESCE(receptor_rfc, '')) = ?)
            """,
            (periodo, rfc_empresa.upper(), rfc_empresa.upper()),
        )
        return int(value or 0)

    value = _sqlite_scalar(
        db_path,
        "SELECT COUNT(*) FROM cfdi WHERE substr(COALESCE(fecha, ''), 1, 7) = ?",
        (periodo,),
    )
    return int(value or 0)


def _count_analytics_kpis_rows(db_path: Path, rfc_empresa: str | None, periodo: str) -> int:
    if not _sqlite_table_exists(db_path, "kpis_mensuales_empresa"):
        return 0

    if rfc_empresa:
        value = _sqlite_scalar(
            db_path,
            "SELECT COUNT(*) FROM kpis_mensuales_empresa WHERE rfc_empresa = ? AND periodo = ?",
            (rfc_empresa.upper(), periodo),
        )
        return int(value or 0)

    value = _sqlite_scalar(
        db_path,
        "SELECT COUNT(*) FROM kpis_mensuales_empresa WHERE periodo = ?",
        (periodo,),
    )
    return int(value or 0)


def _top_row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{row['nombre_counterparty']}</td>"
        f"<td>{row['rfc_counterparty']}</td>"
        f"<td>{row['num_cfdi']}</td>"
        f"<td>{_fmt_currency(row['monto_total_mxn'])}</td>"
        f"<td>{float(row['porcentaje_del_total']):.2f}%</td>"
        "</tr>"
    )


def _empty_row() -> str:
    return "<tr><td colspan='5'>Sin registros relevantes</td></tr>"


def _fmt_currency(value: Any) -> str:
    return f"${float(value or 0):,.2f} MXN"


def _fmt_pct_or_na(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}%"


def _clean_file_list(paths) -> list[Path]:
    return sorted(path for path in paths if not path.name.startswith("~$"))


def _load_monthly_cfdi_frames(periodo: str, rfc_empresa: str) -> dict[str, pd.DataFrame]:
    frames = {
        "df_emitidas": pd.DataFrame(),
        "df_recibidas": pd.DataFrame(),
    }

    period_dir = EXPORTS_DIR / rfc_empresa.upper() / periodo
    csv_files = _clean_file_list(period_dir.rglob("*.csv")) if period_dir.exists() else []
    excel_files = discover_generated_files(rfc_empresa, periodo).get("excel_files", [])

    frames["df_emitidas"] = _load_role_cfdi_frame(csv_files, excel_files, "EMITIDAS")
    frames["df_recibidas"] = _load_role_cfdi_frame(csv_files, excel_files, "RECIBIDAS")

    return frames


def _load_role_cfdi_frame(csv_files: list[Path], excel_files: list[Path], role: str) -> pd.DataFrame:
    csv_path = next((path for path in csv_files if _path_matches_role(path, role)), None)
    if csv_path is not None:
        return _read_cfdi_csv(csv_path)

    excel_path = next((path for path in excel_files if _path_matches_role(path, role)), None)
    if excel_path is not None:
        return _read_cfdi_sheet(excel_path)

    return pd.DataFrame()


def _path_matches_role(path: Path, role: str) -> bool:
    return role.upper() in str(path).upper()


def _read_cfdi_csv(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            path,
            dtype={
                "METODO_PAGO": "string",
                "TIPO_COMPROB": "string",
                "REGIMEN_CODIGO": "string",
            },
        )
    except Exception:
        return pd.DataFrame()
    return _normalize_cfdi_frame(frame)


def _read_cfdi_sheet(path: Path) -> pd.DataFrame:
    try:
        frame = pd.read_excel(path, sheet_name="CFDI")
    except ValueError:
        frame = pd.read_excel(path)
    except Exception:
        return pd.DataFrame()
    return _normalize_cfdi_frame(frame)


def _normalize_cfdi_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    normalized = frame.copy()
    for candidates in (
        ["METODO_PAGO", "MetodoPago", "metodo_pago"],
        ["TIPO_COMPROB", "TipoDeComprobante", "tipo_comprob", "tipo_de_comprobante"],
        ["REGIMEN_CODIGO", "Receptor_RegimenFiscal", "receptor_regimenfiscal", "regimen_codigo"],
    ):
        column = _find_matching_column(normalized, candidates)
        if column is not None:
            normalized[column] = normalized[column].astype("string").str.strip()
    return normalized


def _find_matching_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().upper(): column for column in frame.columns}
    for candidate in candidates:
        match = lookup.get(candidate.strip().upper())
        if match is not None:
            return match
    return None


def _load_alertas_runtime() -> dict[str, Any]:
    try:
        from alertas.app.catalog import nombre_cliente
        from alertas.app.config_validation import validar_config as validar_alertas_config
        from alertas.app.data_access import cargar_datos_cliente_periodo
        from alertas.app.logging_utils import setup_logging as setup_alertas_logging
        from alertas.app.rendering import build_regimen_insight, render_html_cliente
        from alertas.app.rules import evaluar_cliente_periodo
        from alertas.app.settings import MESES_ES as alertas_meses, cargar_clientes, cargar_config
        from alertas.app.storage import HistorialAlertasRepository
        from alertas.app.use_cases import ejecutar_modo_cliente
    except ModuleNotFoundError:
        alertas_root = asset_path("alertas")
        if str(alertas_root) not in sys.path:
            sys.path.insert(0, str(alertas_root))

        from app.catalog import nombre_cliente
        from app.config_validation import validar_config as validar_alertas_config
        from app.data_access import cargar_datos_cliente_periodo
        from app.logging_utils import setup_logging as setup_alertas_logging
        from app.rendering import build_regimen_insight, render_html_cliente
        from app.rules import evaluar_cliente_periodo
        from app.settings import MESES_ES as alertas_meses, cargar_clientes, cargar_config
        from app.storage import HistorialAlertasRepository
        from app.use_cases import ejecutar_modo_cliente

    return {
        "MESES_ES": alertas_meses,
        "HistorialAlertasRepository": HistorialAlertasRepository,
        "build_regimen_insight": build_regimen_insight,
        "cargar_clientes": cargar_clientes,
        "cargar_config": cargar_config,
        "cargar_datos_cliente_periodo": cargar_datos_cliente_periodo,
        "ejecutar_modo_cliente": ejecutar_modo_cliente,
        "evaluar_cliente_periodo": evaluar_cliente_periodo,
        "nombre_cliente": nombre_cliente,
        "render_html_cliente": render_html_cliente,
        "setup_logging": setup_alertas_logging,
        "validar_config": validar_alertas_config,
    }


def _summarize_alert_frame(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {"total": 0.0, "count": 0}

    working = frame.copy()
    if "TIPO_COMPROB" in working.columns:
        tipo = working["TIPO_COMPROB"].astype("string").fillna("").str.upper()
        working = working[tipo.eq("I")].copy()

    total = 0.0
    if "TOTAL" in working.columns:
        total = float(pd.to_numeric(working["TOTAL"], errors="coerce").fillna(0).sum())

    return {"total": round(total, 2), "count": int(len(working))}


def _summarize_alert_levels(alertas: list[Any]) -> dict[str, int]:
    return {
        "alta": sum(1 for alerta in alertas if getattr(alerta, "severidad", "") == "ALTA"),
        "media": sum(1 for alerta in alertas if getattr(alerta, "severidad", "") == "MEDIA"),
        "baja": sum(1 for alerta in alertas if getattr(alerta, "severidad", "") == "BAJA"),
        "total": len(alertas),
    }


def _build_client_alert_text(
    nombre: str,
    rfc: str,
    periodo: str,
    stats_emitidas: dict[str, float | int],
    stats_recibidas: dict[str, float | int],
    regimen_insight: dict[str, Any],
    alertas: list[Any],
) -> str:
    lines = [
        f"Reporte Mensual CFDI - {nombre}",
        f"RFC: {rfc}",
        f"Periodo: {periodo}",
        "",
        f"Ingresos: {_fmt_currency(stats_emitidas['total'])}",
        f"Egresos: {_fmt_currency(stats_recibidas['total'])}",
        f"CFDI emitidos: {int(stats_emitidas['count'])}",
        f"CFDI recibidos: {int(stats_recibidas['count'])}",
    ]

    regimen_display_lines = regimen_insight.get("display_lines") or []
    if regimen_display_lines or regimen_insight.get("headline"):
        lines.extend(
            [
                "",
                "Regimen fiscal receptor:",
            ]
        )
        for line in regimen_display_lines or [str(regimen_insight["headline"])]:
            lines.append(f"- {line}")
        if regimen_insight.get("summary"):
            lines.append(str(regimen_insight["summary"]))
        if regimen_insight.get("warning"):
            lines.append(str(regimen_insight["warning"]))

    lines.extend(
        [
            "",
            "Alertas detectadas:",
        ]
    )

    if alertas:
        for alerta in alertas:
            amount = f" | Monto: {_fmt_currency(getattr(alerta, 'monto_total', 0))}" if getattr(alerta, "monto_total", 0) else ""
            lines.append(
                f"- [{getattr(alerta, 'severidad', 'N/A')}] {getattr(alerta, 'tipo_alerta', 'ALERTA')}: {getattr(alerta, 'resumen', '')}{amount}"
            )
    else:
        lines.append("- Sin alertas relevantes en este periodo.")

    return os.linesep.join(lines)


def _build_alert_pdf_legacy(
    subject: str,
    company_name: str,
    rfc: str,
    periodo: str,
    stats_emitidas: dict[str, float | int],
    stats_recibidas: dict[str, float | int],
    severity_summary: dict[str, int],
    alerts: list[Any],
) -> bytes:
    page_size = (1240, 1754)
    margin_x = 88
    margin_top = 88
    margin_bottom = 88
    palette = {
        "bg": "#F5F7FB",
        "panel": "#FFFFFF",
        "hero": "#102542",
        "hero_text": "#F8FAFC",
        "text": "#1F2937",
        "muted": "#64748B",
        "line": "#D8E2EE",
        "alta": "#DC3545",
        "media": "#FD7E14",
        "baja": "#198754",
        "label": "#E2E8F0",
    }

    title_font = _load_pdf_font(40, bold=True)
    heading_font = _load_pdf_font(24, bold=True)
    body_font = _load_pdf_font(20, bold=False)
    body_bold_font = _load_pdf_font(20, bold=True)
    small_font = _load_pdf_font(17, bold=False)
    metric_value_font = _load_pdf_font(26, bold=True)
    metric_label_font = _load_pdf_font(15, bold=False)

    pages: list[Image.Image] = []
    draw, page = _new_pdf_page(page_size, palette["bg"])
    pages.append(page)
    y = margin_top

    draw.rounded_rectangle((margin_x, y, page_size[0] - margin_x, y + 190), radius=26, fill=palette["hero"])
    draw.text((margin_x + 36, y + 30), "REPORTE DE ALERTAS CFDI", font=small_font, fill=palette["label"])
    draw.text((margin_x + 36, y + 64), company_name, font=title_font, fill=palette["hero_text"])
    draw.text((margin_x + 36, y + 118), f"RFC: {rfc}  |  Periodo: {periodo}", font=body_font, fill=palette["hero_text"])
    draw.text((margin_x + 36, y + 150), subject, font=small_font, fill="#D7E3F4")
    y += 220

    draw.text((margin_x, y), "Resumen del periodo", font=heading_font, fill=palette["text"])
    y += 44

    card_gap = 24
    card_width = (page_size[0] - (margin_x * 2) - card_gap) // 2
    card_height = 120
    metric_cards = [
        ("Ingresos", _fmt_currency(stats_emitidas["total"])),
        ("Egresos", _fmt_currency(stats_recibidas["total"])),
        ("CFDI emitidos", str(int(stats_emitidas["count"]))),
        ("CFDI recibidos", str(int(stats_recibidas["count"]))),
    ]
    for index, (label, value) in enumerate(metric_cards):
        row = index // 2
        col = index % 2
        x0 = margin_x + col * (card_width + card_gap)
        y0 = y + row * (card_height + card_gap)
        draw.rounded_rectangle((x0, y0, x0 + card_width, y0 + card_height), radius=22, fill=palette["panel"], outline=palette["line"], width=2)
        draw.text((x0 + 24, y0 + 22), label.upper(), font=metric_label_font, fill=palette["muted"])
        draw.text((x0 + 24, y0 + 56), value, font=metric_value_font, fill=palette["text"])
    y += (card_height * 2) + card_gap + 38

    draw.text((margin_x, y), "Severidad detectada", font=heading_font, fill=palette["text"])
    y += 46
    sev_cards = [
        ("Alta", severity_summary["alta"], palette["alta"]),
        ("Media", severity_summary["media"], palette["media"]),
        ("Baja", severity_summary["baja"], palette["baja"]),
    ]
    sev_gap = 20
    sev_width = (page_size[0] - (margin_x * 2) - (sev_gap * 2)) // 3
    for index, (label, value, color) in enumerate(sev_cards):
        x0 = margin_x + index * (sev_width + sev_gap)
        y0 = y
        draw.rounded_rectangle((x0, y0, x0 + sev_width, y0 + 90), radius=20, fill=palette["panel"], outline=palette["line"], width=2)
        draw.text((x0 + 22, y0 + 18), label, font=body_bold_font, fill=color)
        draw.text((x0 + 22, y0 + 48), str(int(value)), font=metric_value_font, fill=palette["text"])
    y += 126

    draw.text((margin_x, y), "Alertas incluidas", font=heading_font, fill=palette["text"])
    y += 44

    if not alerts:
        y = _draw_wrapped_text(
            draw,
            "Sin alertas relevantes en este periodo.",
            x=margin_x,
            y=y,
            max_width=page_size[0] - (margin_x * 2),
            font=body_font,
            fill=palette["muted"],
            line_gap=8,
        )
    else:
        for alert in alerts:
            block_height = 126
            if y + block_height > page_size[1] - margin_bottom:
                draw, page = _new_pdf_page(page_size, palette["bg"])
                pages.append(page)
                y = margin_top

            severity = str(getattr(alert, "severidad", "N/A")).upper()
            color = {
                "ALTA": palette["alta"],
                "MEDIA": palette["media"],
                "BAJA": palette["baja"],
            }.get(severity, palette["muted"])

            draw.rounded_rectangle(
                (margin_x, y, page_size[0] - margin_x, y + block_height),
                radius=20,
                fill=palette["panel"],
                outline=palette["line"],
                width=2,
            )
            draw.rounded_rectangle((margin_x + 22, y + 22, margin_x + 150, y + 58), radius=14, fill=color)
            draw.text((margin_x + 45, y + 28), severity, font=small_font, fill="#FFFFFF")
            draw.text((margin_x + 176, y + 22), str(getattr(alert, "tipo_alerta", "ALERTA")), font=body_bold_font, fill=palette["text"])

            resumen = str(getattr(alert, "resumen", "")).strip()
            y_after_resumen = _draw_wrapped_text(
                draw,
                resumen,
                x=margin_x + 176,
                y=y + 54,
                max_width=page_size[0] - margin_x - 210,
                font=body_font,
                fill=palette["text"],
                line_gap=6,
                max_lines=2,
            )

            detalle = str(getattr(alert, "detalle", "")).strip()
            if detalle:
                _draw_wrapped_text(
                    draw,
                    detalle,
                    x=margin_x + 176,
                    y=y_after_resumen + 4,
                    max_width=page_size[0] - margin_x - 210,
                    font=small_font,
                    fill=palette["muted"],
                    line_gap=5,
                    max_lines=2,
                )

            monto = float(getattr(alert, "monto_total", 0) or 0)
            cantidad = int(getattr(alert, "cantidad", 0) or 0)
            footer_text = f"Cantidad: {cantidad}"
            if monto:
                footer_text += f"  |  Monto: {_fmt_currency(monto)}"
            draw.text((margin_x + 176, y + 96), footer_text, font=small_font, fill=palette["muted"])
            y += block_height + 18

    footer_y = page_size[1] - 52
    for page in pages:
        footer_draw = ImageDraw.Draw(page)
        footer_draw.line((margin_x, footer_y - 16, page_size[0] - margin_x, footer_y - 16), fill=palette["line"], width=2)
        footer_draw.text((margin_x, footer_y), "Prueba interna: envio temporal redirigido al correo del director.", font=small_font, fill=palette["muted"])

    output = io.BytesIO()
    rgb_pages = [page.convert("RGB") for page in pages]
    rgb_pages[0].save(output, format="PDF", resolution=150.0, save_all=True, append_images=rgb_pages[1:])
    return output.getvalue()


def _new_pdf_page(page_size: tuple[int, int], background: str) -> tuple[ImageDraw.ImageDraw, Image.Image]:
    page = Image.new("RGB", page_size, background)
    return ImageDraw.Draw(page), page


def _load_pdf_font(size: int, bold: bool) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                r"C:\Windows\Fonts\segoeuib.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
                r"C:\Windows\Fonts\calibrib.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                r"C:\Windows\Fonts\segoeui.ttf",
                r"C:\Windows\Fonts\arial.ttf",
                r"C:\Windows\Fonts\calibri.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill: str,
    line_gap: int = 6,
    max_lines: int | None = None,
) -> int:
    lines = _wrap_text(draw, text, font, max_width)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = lines[-1].rstrip(". ") + "..."

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        probe = f"{current} {word}"
        bbox = draw.textbbox((0, 0), probe, font=font)
        width = bbox[2] - bbox[0]
        if width <= max_width:
            current = probe
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _build_alert_pdf(
    subject: str,
    company_name: str,
    rfc: str,
    periodo: str,
    stats_emitidas: dict[str, float | int],
    stats_recibidas: dict[str, float | int],
    regimen_insight: dict[str, Any],
    severity_summary: dict[str, int],
    alerts: list[Any],
) -> bytes:
    page_size = (1240, 1754)
    margin_x = 78
    margin_top = 72
    margin_bottom = 88
    palette = {
        "bg": "#F5F7FB",
        "panel": "#FFFFFF",
        "hero": "#102542",
        "hero_secondary": "#1A4B84",
        "hero_text": "#F8FAFC",
        "text": "#0F172A",
        "muted": "#64748B",
        "line": "#D9E4F0",
        "shadow": "#E7EEF8",
        "alta": "#DC3545",
        "media": "#FD7E14",
        "baja": "#198754",
        "label": "#DCE6F4",
    }

    title_font = _load_pdf_font(28, bold=True)
    company_font = _load_pdf_font(54, bold=True)
    meta_font = _load_pdf_font(22, bold=True)
    small_font = _load_pdf_font(16, bold=False)
    heading_font = _load_pdf_font(25, bold=True)
    card_label_font = _load_pdf_font(15, bold=True)
    card_value_font = _load_pdf_font(28, bold=True)
    regimen_title_font = _load_pdf_font(20, bold=True)
    regimen_body_font = _load_pdf_font(16, bold=False)
    regimen_note_font = _load_pdf_font(15, bold=False)
    sev_title_font = _load_pdf_font(21, bold=True)
    sev_value_font = _load_pdf_font(30, bold=True)
    alert_title_font = _load_pdf_font(21, bold=True)
    alert_summary_font = _load_pdf_font(18, bold=True)
    alert_detail_font = _load_pdf_font(15, bold=False)
    footer_font = _load_pdf_font(14, bold=False)

    pages: list[Image.Image] = []
    draw, page = _new_pdf_page(page_size, palette["bg"])
    pages.append(page)
    y = margin_top

    hero_height = 206
    _draw_shadowed_rounded_rect(draw, (margin_x, y, page_size[0] - margin_x, y + hero_height), radius=28, fill=palette["hero"], shadow=palette["shadow"])
    logo_image = _load_brand_logo(ALERT_LOGO_PATH, max_width=250, max_height=138)
    logo_reserved_width = (logo_image.width + 36) if logo_image is not None else 280
    left_width = page_size[0] - (margin_x * 2) - logo_reserved_width - 24

    _draw_text_lines(
        draw,
        [
            ("REPORTE DE ALERTAS CFDI", title_font, palette["label"]),
            (company_name, company_font, palette["hero_text"]),
            (f"RFC: {rfc}  |  Periodo: {periodo}", meta_font, palette["hero_text"]),
            (subject, small_font, "#D7E3F4"),
        ],
        x=margin_x + 34,
        y=y + 26,
        max_width=left_width,
        gap=10,
    )

    if logo_image is not None:
        logo_x = page_size[0] - margin_x - logo_image.width - 24
        logo_y = y + (hero_height - logo_image.height) // 2
        page.paste(logo_image, (logo_x, logo_y), logo_image)
    else:
        brand_x = page_size[0] - margin_x - 290
        _draw_text_lines(
            draw,
            [
                ("Sis Rodriguez", _load_pdf_font(24, bold=True), palette["hero_text"]),
                ("Contadores Publicos", _load_pdf_font(24, bold=True), palette["hero_text"]),
            ],
            x=brand_x,
            y=y + 74,
            max_width=250,
            gap=2,
        )

    y += hero_height + 42
    draw.text((margin_x, y), "Resumen del periodo", font=heading_font, fill=palette["text"])
    y += 42

    card_gap = 24
    card_width = (page_size[0] - (margin_x * 2) - card_gap) // 2
    card_height = 124
    metric_cards = [
        ("INGRESOS", _fmt_currency(stats_emitidas["total"])),
        ("EGRESOS", _fmt_currency(stats_recibidas["total"])),
        ("CFDI EMITIDOS", str(int(stats_emitidas["count"]))),
        ("CFDI RECIBIDOS", str(int(stats_recibidas["count"]))),
    ]
    for index, (label, value) in enumerate(metric_cards):
        row = index // 2
        col = index % 2
        x0 = margin_x + col * (card_width + card_gap)
        y0 = y + row * (card_height + 18)
        _draw_shadowed_rounded_rect(draw, (x0, y0, x0 + card_width, y0 + card_height), radius=24, fill=palette["panel"], shadow=palette["shadow"], outline=palette["line"])
        draw.text((x0 + 20, y0 + 20), label, font=card_label_font, fill="#9AA8BA")
        draw.text((x0 + 20, y0 + 60), value, font=card_value_font, fill=palette["text"])
    y += (card_height * 2) + 18 + 26

    regimen_display_lines = regimen_insight.get("display_lines") or [str(regimen_insight.get("headline") or "Sin datos de regimen fiscal en CFDI recibidos.")]
    regimen_line_blocks = [
        _wrap_text(draw, str(line), regimen_title_font, page_size[0] - (margin_x * 2) - 48)
        for line in regimen_display_lines
    ]
    regimen_summary_lines = _wrap_text(draw, str(regimen_insight.get("summary") or ""), regimen_body_font, page_size[0] - (margin_x * 2) - 48)
    regimen_warning_lines = _wrap_text(draw, str(regimen_insight.get("warning") or ""), regimen_note_font, page_size[0] - (margin_x * 2) - 72) if regimen_insight.get("warning") else []
    regimen_lines_height = sum(_measure_multiline_height(draw, block, regimen_title_font, 8) for block in regimen_line_blocks)
    if len(regimen_line_blocks) > 1:
        regimen_lines_height += (len(regimen_line_blocks) - 1) * 8
    regimen_height = max(
        126,
        28
        + regimen_lines_height
        + 12
        + _measure_multiline_height(draw, regimen_summary_lines, regimen_body_font, 8)
        + (_measure_multiline_height(draw, regimen_warning_lines, regimen_note_font, 6) + 18 if regimen_warning_lines else 0)
        + 22,
    )

    _draw_shadowed_rounded_rect(
        draw,
        (margin_x, y, page_size[0] - margin_x, y + regimen_height),
        radius=24,
        fill=palette["panel"],
        shadow=palette["shadow"],
        outline=palette["line"],
    )
    current_y = y + 24
    for index, line in enumerate(regimen_display_lines):
        current_y = _draw_wrapped_text(
            draw,
            str(line),
            x=margin_x + 22,
            y=current_y,
            max_width=page_size[0] - (margin_x * 2) - 48,
            font=regimen_title_font,
            fill=palette["text"],
            line_gap=8,
        )
        if index < len(regimen_display_lines) - 1:
            current_y += 8
    current_y = _draw_wrapped_text(
        draw,
        str(regimen_insight.get("summary") or ""),
        x=margin_x + 22,
        y=current_y + 8,
        max_width=page_size[0] - (margin_x * 2) - 48,
        font=regimen_body_font,
        fill=palette["muted"],
        line_gap=8,
    )
    if regimen_insight.get("warning"):
        warning_fill = palette["alta"] if int(regimen_insight.get("count_616") or 0) > 0 else palette["media"]
        draw.rounded_rectangle(
            (margin_x + 22, current_y + 10, page_size[0] - margin_x - 22, y + regimen_height - 18),
            radius=16,
            fill="#FEF2F2" if int(regimen_insight.get("count_616") or 0) > 0 else "#FFF7E6",
            outline="#FECACA" if int(regimen_insight.get("count_616") or 0) > 0 else "#FAD59A",
            width=2,
        )
        _draw_wrapped_text(
            draw,
            str(regimen_insight["warning"]),
            x=margin_x + 38,
            y=current_y + 22,
            max_width=page_size[0] - (margin_x * 2) - 80,
            font=regimen_note_font,
            fill=warning_fill,
            line_gap=6,
        )
    y += regimen_height + 30

    draw.text((margin_x, y), "Severidad detectada", font=heading_font, fill=palette["text"])
    y += 38
    sev_gap = 18
    sev_width = (page_size[0] - (margin_x * 2) - (sev_gap * 2)) // 3
    for index, (label, value, color) in enumerate(
        [
            ("Alta", severity_summary["alta"], palette["alta"]),
            ("Media", severity_summary["media"], palette["media"]),
            ("Baja", severity_summary["baja"], palette["baja"]),
        ]
    ):
        x0 = margin_x + index * (sev_width + sev_gap)
        y0 = y
        _draw_shadowed_rounded_rect(draw, (x0, y0, x0 + sev_width, y0 + 92), radius=22, fill=palette["panel"], shadow=palette["shadow"], outline=palette["line"])
        draw.text((x0 + 20, y0 + 18), label, font=sev_title_font, fill=color)
        draw.text((x0 + 20, y0 + 48), str(int(value)), font=sev_value_font, fill=palette["text"])
    y += 126

    draw.text((margin_x, y), "Alertas incluidas", font=heading_font, fill=palette["text"])
    y += 40

    if not alerts:
        _draw_shadowed_rounded_rect(draw, (margin_x, y, page_size[0] - margin_x, y + 96), radius=22, fill=palette["panel"], shadow=palette["shadow"], outline=palette["line"])
        draw.text((margin_x + 24, y + 34), "Sin alertas relevantes en este periodo.", font=alert_summary_font, fill=palette["muted"])
        y += 114
    else:
        for alert in alerts:
            severity = str(getattr(alert, "severidad", "N/A")).upper()
            color = {
                "ALTA": palette["alta"],
                "MEDIA": palette["media"],
                "BAJA": palette["baja"],
            }.get(severity, palette["muted"])

            type_text = str(getattr(alert, "tipo_alerta", "ALERTA"))
            resumen = str(getattr(alert, "resumen", "")).strip()
            detalle = str(getattr(alert, "detalle", "")).strip()
            cantidad = int(getattr(alert, "cantidad", 0) or 0)
            monto = float(getattr(alert, "monto_total", 0) or 0)
            footer_text = f"Cantidad: {cantidad}"
            if monto:
                footer_text += f"  |  Monto: {_fmt_currency(monto)}"

            text_x = margin_x + 180
            text_width = page_size[0] - margin_x - text_x - 28
            summary_lines = _wrap_text(draw, resumen, alert_summary_font, text_width)
            detail_lines = _wrap_text(draw, detalle, alert_detail_font, text_width) if detalle else []
            if len(detail_lines) > 6:
                detail_lines = detail_lines[:6]
                detail_lines[-1] = detail_lines[-1].rstrip(". ") + "..."

            title_height = _measure_text_height(draw, type_text, alert_title_font)
            summary_height = _measure_multiline_height(draw, summary_lines, alert_summary_font, 10)
            detail_height = _measure_multiline_height(draw, detail_lines, alert_detail_font, 8)
            footer_height = _measure_text_height(draw, footer_text, footer_font)
            block_height = max(
                176,
                24
                + title_height
                + 16
                + summary_height
                + (16 + detail_height if detail_lines else 0)
                + 18
                + footer_height
                + 24,
            )

            if y + block_height > page_size[1] - margin_bottom:
                draw, page = _new_pdf_page(page_size, palette["bg"])
                pages.append(page)
                y = margin_top

            _draw_shadowed_rounded_rect(draw, (margin_x, y, page_size[0] - margin_x, y + block_height), radius=22, fill=palette["panel"], shadow=palette["shadow"], outline=palette["line"])
            pill_y = y + 22
            draw.rounded_rectangle((margin_x + 22, pill_y, margin_x + 142, pill_y + 38), radius=16, fill=color)
            pill_bbox = draw.textbbox((0, 0), severity, font=small_font)
            pill_text_x = margin_x + 22 + ((120 - (pill_bbox[2] - pill_bbox[0])) // 2)
            draw.text((pill_text_x, pill_y + 9), severity, font=small_font, fill="#FFFFFF")

            title_y = y + 22
            draw.text((text_x, title_y), type_text, font=alert_title_font, fill=palette["text"])
            current_y = title_y + title_height + 14
            current_y = _draw_wrapped_text(
                draw,
                resumen,
                x=text_x,
                y=current_y,
                max_width=text_width,
                font=alert_summary_font,
                fill=palette["text"],
                line_gap=10,
            )
            if detalle:
                current_y = _draw_wrapped_text(
                    draw,
                    detalle,
                    x=text_x,
                    y=current_y + 6,
                    max_width=text_width,
                    font=alert_detail_font,
                    fill=palette["muted"],
                    line_gap=8,
                    max_lines=6,
                )
            footer_y = current_y + 14
            draw.text((text_x, footer_y), footer_text, font=footer_font, fill=palette["muted"])
            y += block_height + 18

    footer_y = page_size[1] - 50
    for page in pages:
        footer_draw = ImageDraw.Draw(page)
        footer_draw.line((margin_x, footer_y - 14, page_size[0] - margin_x, footer_y - 14), fill=palette["line"], width=2)
        footer_draw.text((margin_x, footer_y), "Prueba interna: envio temporal redirigido al correo del director.", font=footer_font, fill=palette["muted"])

    output = io.BytesIO()
    rgb_pages = [page.convert("RGB") for page in pages]
    rgb_pages[0].save(output, format="PDF", resolution=150.0, save_all=True, append_images=rgb_pages[1:])
    return output.getvalue()


def _load_brand_logo(
    logo_path: Path | str | None,
    max_width: int,
    max_height: int,
) -> Image.Image | None:
    path = Path(logo_path) if logo_path is not None else LOGO_PATH
    if not path.exists():
        return None

    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        image = image.crop(bbox)
    image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
    return image


def _draw_shadowed_rounded_rect(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str,
    shadow: str,
    outline: str | None = None,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), radius=radius, fill=shadow)
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2 if outline else 0)


def _draw_text_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont, str]],
    x: int,
    y: int,
    max_width: int,
    gap: int,
) -> int:
    for text, font, fill in lines:
        wrapped = _wrap_text(draw, text, font, max_width)
        for line in wrapped:
            draw.text((x, y), line, font=font, fill=fill)
            y += _measure_text_height(draw, line, font) + gap
    return y


def _measure_text_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> int:
    bbox = draw.textbbox((0, 0), text or "Ag", font=font)
    return bbox[3] - bbox[1]


def _measure_multiline_height(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    gap: int,
) -> int:
    if not lines:
        return 0
    total = 0
    for index, line in enumerate(lines):
        total += _measure_text_height(draw, line, font)
        if index < len(lines) - 1:
            total += gap
    return total
