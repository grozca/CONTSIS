from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from runtime_paths import asset_path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - fallback defensivo cuando Pillow no esta disponible.
    Image = None

from .catalog import nombre_cliente
from .models import Alert, ClientPeriodData
from .settings import MESES_ES


LOGO_PATH = asset_path("src", "assets", "logo_sisrodriguez_isotipo.png")
LOGO_CID = "logo_sisrodriguez"


def hash_alertas(alertas: list[Alert]) -> str:
    contenido = json.dumps([alerta.to_history_payload() for alerta in alertas], sort_keys=True)
    return hashlib.sha256(contenido.encode()).hexdigest()[:16]


def _filter_ingreso_cfdi(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    if "TIPO_COMPROB" not in dataframe.columns:
        return dataframe.copy()
    tipo = dataframe["TIPO_COMPROB"].astype("string").fillna("").str.upper()
    return dataframe[tipo.eq("I")].copy()


def _to_text_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if dataframe.empty or column not in dataframe.columns:
        return pd.Series("", index=dataframe.index, dtype="string")
    return dataframe[column].astype("string").fillna("").str.strip().str.replace(r"\.0+$", "", regex=True)


def _sum_money(dataframe: pd.DataFrame, column: str) -> float:
    if dataframe.empty or column not in dataframe.columns:
        return 0.0
    serie = pd.to_numeric(dataframe[column], errors="coerce").fillna(0)
    return round(float(serie.sum()), 2)


def _build_cfdi_stats(dataframe: pd.DataFrame) -> dict[str, float | int]:
    ingresos = _filter_ingreso_cfdi(dataframe)
    return {
        "total": _sum_money(ingresos, "TOTAL"),
        "subtotal": _sum_money(ingresos, "SUBTOTAL_MXN"),
        "iva": _sum_money(ingresos, "IVA_16_CALC"),
        "count": int(len(ingresos)),
    }


def _build_audit_summary(datos: ClientPeriodData) -> dict[str, float | int | bool]:
    emitidas = _filter_ingreso_cfdi(datos.df_e)
    recibidas = _filter_ingreso_cfdi(datos.df_r)

    regimen_recibidas = _to_text_series(recibidas, "REGIMEN_CODIGO")
    metodo_emitidas = _to_text_series(emitidas, "METODO_PAGO").str.upper()
    forma_emitidas = _to_text_series(emitidas, "FORMA_PAGO")
    metodo_recibidas = _to_text_series(recibidas, "METODO_PAGO").str.upper()
    forma_recibidas = _to_text_series(recibidas, "FORMA_PAGO")

    mask_616 = regimen_recibidas.eq("616")
    mask_pue_error = metodo_emitidas.eq("PUE") & forma_emitidas.eq("99")
    mask_ppd_error = metodo_recibidas.eq("PPD") & forma_recibidas.ne("99")

    audit = {
        "has_error": False,
        "count_616": int(mask_616.sum()),
        "count_pue_error": int(mask_pue_error.sum()),
        "count_ppd_error": int(mask_ppd_error.sum()),
        "ingresos_pue": _sum_money(emitidas[metodo_emitidas.eq("PUE")], "TOTAL"),
        "ingresos_ppd": _sum_money(emitidas[metodo_emitidas.eq("PPD")], "TOTAL"),
        "egresos_pue": _sum_money(recibidas[metodo_recibidas.eq("PUE")], "TOTAL"),
        "egresos_ppd": _sum_money(recibidas[metodo_recibidas.eq("PPD")], "TOTAL"),
    }
    audit["has_error"] = bool(
        audit["count_616"] > 0 or audit["count_pue_error"] > 0 or audit["count_ppd_error"] > 0
    )
    return audit


def _build_discrepancy_text(ingresos_total: float, egresos_total: float) -> str:
    if ingresos_total <= 0 and egresos_total <= 0:
        return "No se detectaron ingresos ni egresos tipo I en el periodo."
    if ingresos_total > 0 and egresos_total > 0:
        diferencia = ingresos_total - egresos_total
        if abs(diferencia) < 0.01:
            return "Los ingresos y egresos se encuentran equilibrados en el periodo."
        if diferencia > 0:
            porcentaje = (diferencia / egresos_total) * 100 if egresos_total else 100.0
            return f"Los ingresos superan a los egresos en {porcentaje:,.1f}%."
        porcentaje = (abs(diferencia) / ingresos_total) * 100 if ingresos_total else 100.0
        return f"Los egresos superan a los ingresos en {porcentaje:,.1f}%."
    if ingresos_total > 0:
        return "Se detectaron ingresos, pero no egresos tipo I en el periodo."
    return "Se detectaron egresos, pero no ingresos tipo I en el periodo."


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _find_first_column(dataframe: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().upper(): column for column in dataframe.columns}
    for candidate in candidates:
        match = lookup.get(candidate.strip().upper())
        if match is not None:
            return match
    return None


def _format_regimen_label(code: object, desc: object) -> str:
    code_text = str(code or "").strip().replace(".0", "")
    desc_text = str(desc or "").strip()
    if code_text and desc_text and desc_text.upper() != code_text.upper():
        return f"{code_text} - {desc_text}"
    if code_text:
        return code_text
    if desc_text:
        return desc_text
    return "Sin regimen"

def build_regimen_insight(datos: ClientPeriodData) -> dict[str, Any]:
    recibidas = _filter_ingreso_cfdi(datos.df_r)
    if recibidas.empty:
        return {
            "has_data": False,
            "headline": "Sin datos de regimen fiscal en CFDI recibidos.",
            "summary": "No se detectaron CFDI recibidos tipo I para analizar regimen fiscal.",
            "warning": None,
            "mixed": False,
            "count_616": 0,
            "items": [],
            "display_items": [],
            "display_lines": ["Sin datos de regimen fiscal en CFDI recibidos."],
            "total_cfdi": 0,
        }

    code_col = _find_first_column(recibidas, ["REGIMEN_CODIGO", "RECEPTOR_REGIMENFISCAL", "REGIMEN_FISCAL"])
    desc_col = _find_first_column(recibidas, ["REGIMEN_DESC", "RECEPTOR_REGIMEN_DESC"])
    total_col = _find_first_column(recibidas, ["TOTAL", "TOTAL_MXN", "MONTO_TOTAL_MXN"])

    if code_col is None and desc_col is None:
        return {
            "has_data": False,
            "headline": "Sin datos de regimen fiscal en CFDI recibidos.",
            "summary": "Los XML recibidos del periodo no traen columnas de regimen fiscal disponibles.",
            "warning": None,
            "mixed": False,
            "count_616": 0,
            "items": [],
            "display_items": [],
            "display_lines": ["Sin datos de regimen fiscal en CFDI recibidos."],
            "total_cfdi": int(len(recibidas)),
        }

    prepared = recibidas.copy()
    if total_col is not None:
        prepared["__weight"] = pd.to_numeric(prepared[total_col], errors="coerce").fillna(0.0)
    else:
        prepared["__weight"] = 1.0
    prepared["__regimen_code"] = _to_text_series(prepared, code_col) if code_col else pd.Series("", index=prepared.index, dtype="string")
    prepared["__regimen_label"] = prepared.apply(
        lambda row: _format_regimen_label(
            row.get(code_col) if code_col else None,
            row.get(desc_col) if desc_col else None,
        ),
        axis=1,
    )

    grouped = (
        prepared.groupby("__regimen_label", dropna=False)
        .agg(
            total=("__weight", "sum"),
            count=("__regimen_label", "size"),
            code=("__regimen_code", lambda serie: next((str(item).strip() for item in serie if str(item).strip()), "")),
        )
        .reset_index()
        .rename(columns={"__regimen_label": "label"})
        .sort_values(["count", "total"], ascending=[False, False])
        .reset_index(drop=True)
    )

    if grouped.empty:
        return {
            "has_data": False,
            "headline": "Sin datos de regimen fiscal en CFDI recibidos.",
            "summary": "No fue posible construir la distribucion de regimenes para este periodo.",
            "warning": None,
            "mixed": False,
            "count_616": 0,
            "items": [],
            "display_items": [],
            "display_lines": ["Sin datos de regimen fiscal en CFDI recibidos."],
            "total_cfdi": int(len(recibidas)),
        }

    count_total = int(grouped["count"].sum())
    count_base = float(count_total or 1)

    items = [
        {
            "label": str(row["label"]),
            "code": str(row["code"] or "").strip(),
            "total": round(float(row["total"] or 0), 2),
            "count": int(row["count"] or 0),
            "share_pct": round((int(row["count"] or 0) / count_base) * 100, 1),
        }
        for _, row in grouped.iterrows()
    ]

    primary = items[0]
    others = items[1:]
    count_616 = int(prepared["__regimen_code"].eq("616").sum()) if "__regimen_code" in prepared.columns else 0
    other_count = max(count_total - int(primary["count"]), 0)
    display_items = sorted(items, key=lambda item: (item["share_pct"], item["count"], item["label"]))
    display_lines = [f"{item['label']}: {item['count']} CFDI" for item in display_items]

    warning = None
    if count_616 > 0:
        warning = f"Alerta: {count_616} {_pluralize(count_616, 'CFDI recibido', 'CFDI recibidos')} con 616 - Sin obligaciones fiscales."
    elif others:
        warning = f"Revision recomendada: {other_count} CFDI con regimen distinto al dominante."

    return {
        "has_data": True,
        "headline": display_lines[0],
        "summary": f"{count_total} {_pluralize(count_total, 'CFDI recibido', 'CFDI recibidos')} con regimen fiscal identificado.",
        "warning": warning,
        "mixed": bool(others),
        "count_616": count_616,
        "items": items,
        "display_items": display_items,
        "display_lines": display_lines,
        "total_cfdi": count_total,
    }


def _get_logo_data_uri() -> str | None:
    if not LOGO_PATH.exists():
        return None
    logo_bytes = LOGO_PATH.read_bytes()
    if Image is not None:
        try:
            with Image.open(LOGO_PATH) as image:
                image = image.convert("RGBA")
                alpha = image.getchannel("A")
                bbox = alpha.getbbox()
                if bbox:
                    image = image.crop(bbox)
                image.thumbnail((170, 64), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True, compress_level=9)
                logo_bytes = output.getvalue()
        except Exception:
            pass

    encoded = base64.b64encode(logo_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _get_logo_src(logo_mode: str = "data_uri") -> str | None:
    if logo_mode == "cid":
        return f"cid:{LOGO_CID}" if LOGO_PATH.exists() else None
    return _get_logo_data_uri()


def render_html_ejecutivo(alertas: list[Alert], periodo: str, clientes: dict[str, Any]) -> str:
    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")

    por_rfc: dict[str, list[Alert]] = {}
    for alerta in alertas:
        por_rfc.setdefault(alerta.rfc, []).append(alerta)

    colores = {"ALTA": "#DC3545", "MEDIA": "#FD7E14", "BAJA": "#198754"}

    def badge(severidad: str) -> str:
        color = colores.get(severidad, "#6C757D")
        return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:bold">{severidad}</span>'

    filas_resumen = ""
    for rfc, alertas_rfc in por_rfc.items():
        nombre = nombre_cliente(rfc, clientes)
        altas = sum(1 for alerta in alertas_rfc if alerta.severidad == "ALTA")
        medias = sum(1 for alerta in alertas_rfc if alerta.severidad == "MEDIA")
        bajas = sum(1 for alerta in alertas_rfc if alerta.severidad == "BAJA")
        monto = sum(alerta.monto_total for alerta in alertas_rfc)
        principal = alertas_rfc[0].resumen
        if len(principal) > 60:
            principal = f"{principal[:60]}..."
        filas_resumen += f"""
        <tr style="border-bottom:1px solid #DEE2E6">
          <td style="padding:8px">{badge(alertas_rfc[0].severidad)}</td>
          <td style="padding:8px"><b>{nombre}</b><br><small style="color:#6C757D">{rfc}</small></td>
          <td style="padding:8px;text-align:center">
            {'<span style="color:#DC3545;font-weight:bold">'+str(altas)+'</span>' if altas else '<span style="color:#AAA">0</span>'}
            /
            {'<span style="color:#FD7E14">'+str(medias)+'</span>' if medias else '<span style="color:#AAA">0</span>'}
            /
            {'<span style="color:#198754">'+str(bajas)+'</span>' if bajas else '<span style="color:#AAA">0</span>'}
          </td>
          <td style="padding:8px;text-align:right">${monto:,.2f}</td>
          <td style="padding:8px;color:#555;font-size:12px">{principal}</td>
        </tr>"""

    detalle_html = ""
    for rfc, alertas_rfc in por_rfc.items():
        nombre = nombre_cliente(rfc, clientes)
        filas_detalle = ""
        for alerta in alertas_rfc:
            filas_detalle += f"""
            <tr style="border-bottom:1px solid #EEE">
              <td style="padding:8px">{badge(alerta.severidad)}</td>
              <td style="padding:8px"><b>{alerta.tipo_alerta}</b><br>
                <small style="color:#555">{alerta.resumen}</small><br>
                <small style="color:#888;font-style:italic">{alerta.detalle}</small>
              </td>
              <td style="padding:8px;text-align:center">{alerta.cantidad}</td>
              <td style="padding:8px;text-align:right">${alerta.monto_total:,.2f}</td>
            </tr>"""
        detalle_html += f"""
        <h3 style="margin:20px 0 6px;color:#1F3864;font-size:14px">{nombre} - {rfc}</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;background:white">
          <thead><tr style="background:#F1F3F5;font-size:12px;color:#6C757D">
            <th style="padding:8px;text-align:left;width:80px">Severidad</th>
            <th style="padding:8px;text-align:left">Alerta</th>
            <th style="padding:8px;text-align:center;width:60px">Cant.</th>
            <th style="padding:8px;text-align:right;width:120px">Monto MXN</th>
          </tr></thead>
          <tbody>{filas_detalle}</tbody>
        </table>"""

    altas_totales = sum(1 for alerta in alertas if alerta.severidad == "ALTA")
    medias_totales = sum(1 for alerta in alertas if alerta.severidad == "MEDIA")
    bajas_totales = sum(1 for alerta in alertas if alerta.severidad == "BAJA")

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:900px;margin:0 auto">
      <div style="background:#1F3864;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">CONTSIS - Reporte de Alertas</h2>
        <p style="margin:4px 0 0;opacity:0.8">Sis Rodriguez Contadores Publicos | {mes_label} {year} | Generado {fecha_generacion}</p>
      </div>
      <div style="background:#F8F9FA;padding:16px;display:flex;gap:12px;flex-wrap:wrap">
        <div style="background:white;border-left:4px solid #DC3545;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#DC3545">{altas_totales}</div>
          <div style="font-size:11px;color:#6C757D">ALTA</div>
        </div>
        <div style="background:white;border-left:4px solid #FD7E14;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#FD7E14">{medias_totales}</div>
          <div style="font-size:11px;color:#6C757D">MEDIA</div>
        </div>
        <div style="background:white;border-left:4px solid #198754;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#198754">{bajas_totales}</div>
          <div style="font-size:11px;color:#6C757D">BAJA</div>
        </div>
        <div style="background:white;border-left:4px solid #2E75B6;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#2E75B6">{len(por_rfc)}</div>
          <div style="font-size:11px;color:#6C757D">EMPRESAS</div>
        </div>
      </div>
      <div style="padding:16px;background:white">
        <h3 style="color:#1F3864;margin:0 0 12px">Resumen ejecutivo por empresa</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead><tr style="background:#1F3864;color:white">
            <th style="padding:10px;text-align:left;width:80px">Prioridad</th>
            <th style="padding:10px;text-align:left">Empresa</th>
            <th style="padding:10px;text-align:center;width:100px">Alta/Media/Baja</th>
            <th style="padding:10px;text-align:right;width:130px">Monto MXN</th>
            <th style="padding:10px;text-align:left">Principal alerta</th>
          </tr></thead>
          <tbody>{filas_resumen}</tbody>
        </table>
      </div>
      <div style="padding:16px;background:white">
        <h3 style="color:#1F3864;margin:0 0 12px">Detalle por empresa</h3>
        {detalle_html}
      </div>
      <div style="background:#F8F9FA;padding:12px;border-radius:0 0 8px 8px;font-size:11px;color:#6C757D;text-align:center">
        CONTSIS v2.0 | Sis Rodriguez Contadores Publicos | Uso interno exclusivo
      </div>
    </div>
    """


def render_html_cliente(
    rfc: str,
    periodo: str,
    alertas_cliente: list[Alert],
    datos: ClientPeriodData,
    clientes: dict[str, Any],
    logo_mode: str = "data_uri",
) -> str:
    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    nombre = nombre_cliente(rfc, clientes)
    fecha_generacion = datetime.now().strftime("%d/%m/%Y")
    colores = {"ALTA": "#DC3545", "MEDIA": "#FD7E14", "BAJA": "#198754"}
    stats_emitidas = _build_cfdi_stats(datos.df_e)
    stats_recibidas = _build_cfdi_stats(datos.df_r)
    logo_src = _get_logo_src(logo_mode)
    audit = _build_audit_summary(datos)
    regimen_insight = build_regimen_insight(datos)
    discrepancy_text = _build_discrepancy_text(
        float(stats_emitidas["total"]),
        float(stats_recibidas["total"]),
    )
    alertas_visibles = [alerta for alerta in alertas_cliente if alerta.severidad in ("ALTA", "MEDIA")]
    def _section_row(content: str) -> str:
        return f"""
        <tr>
          <td style="padding-top:18px;">
            {content}
          </td>
        </tr>
        """

    def _card_table(title: str, body_html: str, *, border_color: str = "#E2E8F0", background: str = "#FFFFFF", title_color: str = "#0F172A") -> str:
        return (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;background:{background};border:1px solid {border_color};border-radius:22px;">'
            f'<tr><td style="padding:20px 22px;">'
            f'<div style="margin:0 0 14px;color:{title_color};font-size:18px;line-height:1.3;font-weight:700;">{title}</div>'
            f"{body_html}"
            "</td></tr></table>"
        )

    filas_alertas = ""
    for alerta in alertas_visibles:
        color = colores.get(alerta.severidad, "#6C757D")
        monto_total = float(alerta.monto_total or 0)
        detalle_html = (
            f'<div style="font-size:12px;line-height:1.6;color:#64748B;margin-top:6px;">{alerta.detalle}</div>'
            if alerta.detalle
            else ""
        )
        monto_html = f"${monto_total:,.2f}" if monto_total > 0 else "-"
        filas_alertas += f"""
        <tr>
          <td style="padding:12px 8px;border-bottom:1px solid #E2E8F0;vertical-align:top;">
            <span style="display:inline-block;background:{color};color:#FFFFFF;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;">{alerta.severidad}</span>
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #E2E8F0;vertical-align:top;">
            <div style="font-size:13px;font-weight:700;color:#0F172A;">{alerta.tipo_alerta}</div>
            <div style="font-size:13px;line-height:1.6;color:#334155;margin-top:2px;">{alerta.resumen}</div>
            {detalle_html}
          </td>
          <td style="padding:12px 8px;border-bottom:1px solid #E2E8F0;text-align:center;vertical-align:top;">{int(alerta.cantidad or 0)}</td>
          <td style="padding:12px 8px;border-bottom:1px solid #E2E8F0;text-align:right;vertical-align:top;">{monto_html}</td>
        </tr>"""
    if not filas_alertas:
        filas_alertas = """
        <tr>
          <td colspan="4" style="padding:14px 10px;color:#198754;text-align:center;font-size:13px;font-weight:700;">
            Sin alertas relevantes este periodo.
          </td>
        </tr>"""

    audit_rows = ""
    if int(audit["count_616"]) > 0:
        audit_rows += (
            f"<tr><td style='padding:0 0 10px;font-size:14px;line-height:1.75;color:#7F1D1D;'>"
            f"<strong>Riesgo de deducibilidad (Regimen 616):</strong> Se detectaron <strong>{int(audit['count_616'])}</strong> "
            f"{_pluralize(int(audit['count_616']), 'factura recibida', 'facturas recibidas')} con Regimen 616."
            "</td></tr>"
        )
    if int(audit["count_pue_error"]) > 0:
        audit_rows += (
            f"<tr><td style='padding:0 0 10px;font-size:14px;line-height:1.75;color:#7F1D1D;'>"
            f"<strong>Inconsistencia PUE:</strong> <strong>{int(audit['count_pue_error'])}</strong> "
            f"{_pluralize(int(audit['count_pue_error']), 'factura emitida', 'facturas emitidas')} con PUE y forma de pago 99."
            "</td></tr>"
        )
    if int(audit["count_ppd_error"]) > 0:
        audit_rows += (
            f"<tr><td style='padding:0;font-size:14px;line-height:1.75;color:#7F1D1D;'>"
            f"<strong>Inconsistencia PPD:</strong> <strong>{int(audit['count_ppd_error'])}</strong> "
            f"{_pluralize(int(audit['count_ppd_error']), 'factura recibida', 'facturas recibidas')} con PPD y forma distinta a 99."
            "</td></tr>"
        )

    audit_html = ""
    if audit_rows:
        audit_html = _section_row(
            _card_table(
                "Alertas de auditoria",
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='width:100%;border-collapse:collapse;'>{audit_rows}</table>",
                border_color="#FECACA",
                background="#FEF2F2",
                title_color="#991B1B",
            )
        )

    liquidity_html = _section_row(
        _card_table(
            "Estado de liquidez (metodos de pago)",
            f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
              <tr>
                <td width="50%" style="width:50%;padding:0 14px 0 0;vertical-align:top;">
                  <div style="font-size:14px;color:#334155;font-weight:700;margin-bottom:10px;">Dinero por cobrar (facturado):</div>
                  <div style="font-size:14px;line-height:1.9;color:#334155;"><strong style="color:#15803D;">Cobrado (PUE):</strong> ${float(audit['ingresos_pue']):,.2f} MXN</div>
                  <div style="font-size:14px;line-height:1.9;color:#334155;"><strong style="color:#C2410C;">A credito (PPD):</strong> ${float(audit['ingresos_ppd']):,.2f} MXN</div>
                </td>
                <td width="50%" style="width:50%;padding:0 0 0 14px;vertical-align:top;">
                  <div style="font-size:14px;color:#334155;font-weight:700;margin-bottom:10px;">Dinero por pagar (comprado):</div>
                  <div style="font-size:14px;line-height:1.9;color:#334155;"><strong style="color:#15803D;">Pagado (PUE):</strong> ${float(audit['egresos_pue']):,.2f} MXN</div>
                  <div style="font-size:14px;line-height:1.9;color:#334155;"><strong style="color:#C2410C;">A credito (PPD):</strong> ${float(audit['egresos_ppd']):,.2f} MXN</div>
                </td>
              </tr>
            </table>
            """,
        )
    )

    regimen_display_lines = regimen_insight.get("display_lines") or [str(regimen_insight.get("headline") or "Sin datos de regimen fiscal en CFDI recibidos.")]
    regimen_lines_html = "".join(
        f'<div style="font-size:18px;line-height:1.5;font-weight:700;color:#0F172A;margin-top:{0 if index == 0 else 6}px;">{line}</div>'
        for index, line in enumerate(regimen_display_lines)
    )
    regimen_note_html = ""
    if regimen_insight.get("warning"):
        warning_color = "#991B1B" if int(regimen_insight.get("count_616") or 0) > 0 else "#9A6700"
        warning_bg = "#FEF2F2" if int(regimen_insight.get("count_616") or 0) > 0 else "#FFF7E6"
        warning_border = "#FECACA" if int(regimen_insight.get("count_616") or 0) > 0 else "#FAD59A"
        regimen_note_html += (
            f'<div style="font-size:13px;line-height:1.7;color:{warning_color};margin-top:10px;padding:10px 12px;background:{warning_bg};border:1px solid {warning_border};border-radius:12px;">'
            f"{regimen_insight['warning']}</div>"
        )

    regimen_html = _section_row(
        _card_table(
            "Regimen fiscal receptor",
            (
                f"{regimen_lines_html}"
                f'<div style="font-size:13px;line-height:1.7;color:#64748B;margin-top:8px;">{regimen_insight["summary"]}</div>'
                f"{regimen_note_html}"
            ),
        )
    )

    kpis_html = _section_row(
        _card_table(
            "KPIs clave del mes",
            f"""
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:separate;border-spacing:0;">
              <tr>
                <td width="50%" style="width:50%;padding:0 10px 0 0;vertical-align:top;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:16px;">
                    <tr><td style="padding:16px;">
                      <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.04em;">Ingresos</div>
                      <div style="font-size:22px;line-height:1.35;font-weight:800;color:#0F766E;margin-top:6px;">${float(stats_emitidas['total']):,.2f} MXN</div>
                    </td></tr>
                  </table>
                </td>
                <td width="50%" style="width:50%;padding:0 0 0 10px;vertical-align:top;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:16px;">
                    <tr><td style="padding:16px;">
                      <div style="font-size:11px;color:#64748B;text-transform:uppercase;letter-spacing:0.04em;">Egresos</div>
                      <div style="font-size:22px;line-height:1.35;font-weight:800;color:#B91C1C;margin-top:6px;">${float(stats_recibidas['total']):,.2f} MXN</div>
                    </td></tr>
                  </table>
                </td>
              </tr>
            </table>
            <div style="font-size:14px;line-height:1.8;color:#475569;margin-top:14px;"><strong>Discrepancia:</strong> {discrepancy_text}</div>
            """,
        )
    )

    logo_html = (
        f'<img src="{logo_src}" width="130" alt="Sis Rodriguez Contadores Publicos" style="display:block;width:130px;max-width:130px;height:auto;border:0;outline:none;text-decoration:none;">'
        if logo_src
        else '<div style="font-size:18px;line-height:1.35;font-weight:700;color:#FFFFFF;text-align:right;">Sis Rodriguez<br>Contadores Publicos</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="es">
  <body style="margin:0;padding:0;background-color:#F4F7FB;font-family:Arial,sans-serif;color:#0F172A;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;background-color:#F4F7FB;">
      <tr>
        <td align="center" style="padding:24px 12px;">
          <table role="presentation" width="760" cellpadding="0" cellspacing="0" style="width:760px;max-width:760px;border-collapse:separate;background:#FFFFFF;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden;">
            <tr>
              <td style="background:#1F3864;padding:22px 20px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                  <tr>
                    <td style="padding-right:16px;vertical-align:middle;">
                      <div style="font-size:18px;line-height:1.35;font-weight:700;color:#FFFFFF;">Reporte Mensual de CFDI</div>
                      <div style="font-size:14px;line-height:1.6;color:#DCE6F4;margin-top:6px;">{nombre} &middot; {mes_label} {year}</div>
                    </td>
                    <td width="150" style="width:150px;vertical-align:middle;text-align:right;">
                      {logo_html}
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="padding:22px 20px 24px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;">
                  <tr>
                    <td style="font-size:14px;line-height:1.75;color:#374151;padding:0;">
                      Estimado cliente, a continuacion presentamos el resumen de sus Comprobantes Fiscales
                      Digitales correspondientes al periodo <strong>{mes_label} {year}</strong>.
                    </td>
                  </tr>
                  {regimen_html}
                  {audit_html}
                  {liquidity_html}
                  {kpis_html}
                  <tr>
                    <td style="padding-top:22px;">
                      <div style="color:#2E75B6;font-size:14px;line-height:1.4;font-weight:700;border-bottom:2px solid #2E75B6;padding-bottom:4px;">Resumen Fiscal</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:12px;">
                      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;font-size:13px;">
                        <thead>
                          <tr style="background:#1F3864;color:#FFFFFF;">
                            <th style="padding:8px;text-align:left;">Concepto</th>
                            <th style="padding:8px;text-align:right;">Facturas emitidas</th>
                            <th style="padding:8px;text-align:right;">Facturas recibidas</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr style="background:#F8FAFC;">
                            <td style="padding:8px;">Subtotal</td>
                            <td style="padding:8px;text-align:right;">${stats_emitidas['subtotal']:,.2f}</td>
                            <td style="padding:8px;text-align:right;">${stats_recibidas['subtotal']:,.2f}</td>
                          </tr>
                          <tr>
                            <td style="padding:8px;">IVA (16%)</td>
                            <td style="padding:8px;text-align:right;">${stats_emitidas['iva']:,.2f}</td>
                            <td style="padding:8px;text-align:right;">${stats_recibidas['iva']:,.2f}</td>
                          </tr>
                          <tr style="background:#FFF9C4;font-weight:700;">
                            <td style="padding:8px;">Total</td>
                            <td style="padding:8px;text-align:right;">${stats_emitidas['total']:,.2f}</td>
                            <td style="padding:8px;text-align:right;">${stats_recibidas['total']:,.2f}</td>
                          </tr>
                          <tr style="background:#F8FAFC;">
                            <td style="padding:8px;">No. de CFDIs</td>
                            <td style="padding:8px;text-align:right;">{stats_emitidas['count']}</td>
                            <td style="padding:8px;text-align:right;">{stats_recibidas['count']}</td>
                          </tr>
                        </tbody>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:22px;">
                      <div style="color:#2E75B6;font-size:14px;line-height:1.4;font-weight:700;border-bottom:2px solid #2E75B6;padding-bottom:4px;">Puntos de atencion</div>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:12px;">
                      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="width:100%;border-collapse:collapse;font-size:13px;">
                        <thead>
                          <tr style="background:#F8FAFC;color:#334155;">
                            <th style="padding:8px;text-align:left;width:90px;">Severidad</th>
                            <th style="padding:8px;text-align:left;">Alerta</th>
                            <th style="padding:8px;text-align:center;width:70px;">Cant.</th>
                            <th style="padding:8px;text-align:right;width:110px;">Monto MXN</th>
                          </tr>
                        </thead>
                        <tbody>{filas_alertas}</tbody>
                      </table>
                    </td>
                  </tr>
                  <tr>
                    <td style="padding-top:20px;font-size:12px;line-height:1.8;color:#64748B;">
                      Para cualquier aclaracion, comuniquese con Sis Rodriguez Contadores Publicos.
                      Este reporte fue generado el {fecha_generacion}.
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
            <tr>
              <td style="background:#F8FAFC;padding:10px 14px;text-align:center;font-size:11px;line-height:1.6;color:#64748B;">
                Sis Rodriguez Contadores Publicos &middot; Puebla, Mexico &middot; Prueba interna redirigida al correo del director
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""
