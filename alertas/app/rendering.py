from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import pandas as pd

from .catalog import nombre_cliente
from .models import Alert, ClientPeriodData
from .settings import MESES_ES


def hash_alertas(alertas: list[Alert]) -> str:
    contenido = json.dumps([alerta.to_history_payload() for alerta in alertas], sort_keys=True)
    return hashlib.sha256(contenido.encode()).hexdigest()[:16]


def render_html_ejecutivo(alertas: list[Alert], periodo: str, clientes: dict[str, Any]) -> str:
    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    fecha_generacion = datetime.now().strftime("%d/%m/%Y %H:%M")

    por_rfc: dict[str, list[Alert]] = {}
    for alerta in alertas:
        por_rfc.setdefault(alerta.rfc, []).append(alerta)

    colores = {"ALTA": "#dc3545", "MEDIA": "#fd7e14", "BAJA": "#198754"}

    def badge(severidad: str) -> str:
        color = colores.get(severidad, "#6c757d")
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
        <tr style="border-bottom:1px solid #dee2e6">
          <td style="padding:8px">{badge(alertas_rfc[0].severidad)}</td>
          <td style="padding:8px"><b>{nombre}</b><br><small style="color:#6c757d">{rfc}</small></td>
          <td style="padding:8px;text-align:center">
            {'<span style="color:#dc3545;font-weight:bold">'+str(altas)+'</span>' if altas else '<span style="color:#aaa">0</span>'}
            /
            {'<span style="color:#fd7e14">'+str(medias)+'</span>' if medias else '<span style="color:#aaa">0</span>'}
            /
            {'<span style="color:#198754">'+str(bajas)+'</span>' if bajas else '<span style="color:#aaa">0</span>'}
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
            <tr style="border-bottom:1px solid #eee">
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
          <thead><tr style="background:#f1f3f5;font-size:12px;color:#6c757d">
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
        <p style="margin:4px 0 0;opacity:0.8">Sis Rodriguez Contadores Publicos · {mes_label} {year} · Generado {fecha_generacion}</p>
      </div>
      <div style="background:#f8f9fa;padding:16px;display:flex;gap:12px;flex-wrap:wrap">
        <div style="background:white;border-left:4px solid #dc3545;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#dc3545">{altas_totales}</div>
          <div style="font-size:11px;color:#6c757d">ALTA</div>
        </div>
        <div style="background:white;border-left:4px solid #fd7e14;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#fd7e14">{medias_totales}</div>
          <div style="font-size:11px;color:#6c757d">MEDIA</div>
        </div>
        <div style="background:white;border-left:4px solid #198754;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#198754">{bajas_totales}</div>
          <div style="font-size:11px;color:#6c757d">BAJA</div>
        </div>
        <div style="background:white;border-left:4px solid #2E75B6;padding:12px 20px;border-radius:4px;min-width:80px">
          <div style="font-size:28px;font-weight:bold;color:#2E75B6">{len(por_rfc)}</div>
          <div style="font-size:11px;color:#6c757d">EMPRESAS</div>
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
      <div style="background:#f8f9fa;padding:12px;border-radius:0 0 8px 8px;font-size:11px;color:#6c757d;text-align:center">
        CONTSIS v2.0 · Sis Rodriguez Contadores Publicos · Uso interno exclusivo
      </div>
    </div>
    """


def render_html_cliente(
    rfc: str,
    periodo: str,
    alertas_cliente: list[Alert],
    datos: ClientPeriodData,
    clientes: dict[str, Any],
) -> str:
    year, month = periodo.split("-")
    mes_label = MESES_ES.get(int(month), month).capitalize()
    nombre = nombre_cliente(rfc, clientes)
    fecha_generacion = datetime.now().strftime("%d/%m/%Y")
    colores = {"ALTA": "#dc3545", "MEDIA": "#fd7e14", "BAJA": "#198754"}

    def stats(dataframe: pd.DataFrame) -> dict[str, float | int]:
        if dataframe.empty:
            return {"total": 0, "subtotal": 0, "iva": 0, "count": 0}
        ingresos = dataframe[dataframe["TIPO_COMPROB"] == "I"] if "TIPO_COMPROB" in dataframe.columns else dataframe
        return {
            "total": round(ingresos["TOTAL"].sum(), 2) if "TOTAL" in ingresos.columns else 0,
            "subtotal": round(ingresos["SUBTOTAL_MXN"].sum(), 2) if "SUBTOTAL_MXN" in ingresos.columns else 0,
            "iva": round(ingresos["IVA_16_CALC"].sum(), 2) if "IVA_16_CALC" in ingresos.columns else 0,
            "count": len(ingresos),
        }

    stats_emitidas = stats(datos.df_e)
    stats_recibidas = stats(datos.df_r)
    alertas_visibles = [alerta for alerta in alertas_cliente if alerta.severidad in ("ALTA", "MEDIA")]

    filas_alertas = ""
    for alerta in alertas_visibles:
        color = colores.get(alerta.severidad, "#6c757d")
        filas_alertas += f"""
        <tr style="border-bottom:1px solid #eee">
          <td style="padding:8px">
            <span style="background:{color};color:white;padding:2px 6px;border-radius:3px;font-size:11px">{alerta.severidad}</span>
          </td>
          <td style="padding:8px;font-size:13px">{alerta.resumen}</td>
        </tr>"""
    if not filas_alertas:
        filas_alertas = '<tr><td colspan="2" style="padding:12px;color:#198754;text-align:center">Sin alertas relevantes este periodo</td></tr>'

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:750px;margin:0 auto">
      <div style="background:#1F3864;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0;font-size:18px">Reporte Mensual de CFDI</h2>
        <p style="margin:4px 0 0;opacity:0.8">{nombre} · {mes_label} {year}</p>
      </div>
      <div style="background:white;padding:20px">
        <p style="color:#555;font-size:13px">
          Estimado cliente, a continuacion presentamos el resumen de sus Comprobantes Fiscales
          Digitales correspondientes al periodo <b>{mes_label} {year}</b>.
        </p>
        <h3 style="color:#2E75B6;font-size:14px;border-bottom:2px solid #2E75B6;padding-bottom:4px">Resumen Fiscal</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:16px">
          <thead><tr style="background:#1F3864;color:white">
            <th style="padding:8px;text-align:left">Concepto</th>
            <th style="padding:8px;text-align:right">Facturas emitidas</th>
            <th style="padding:8px;text-align:right">Facturas recibidas</th>
          </tr></thead>
          <tbody>
            <tr style="background:#f8f9fa"><td style="padding:8px">Subtotal</td>
              <td style="padding:8px;text-align:right">${stats_emitidas['subtotal']:,.2f}</td>
              <td style="padding:8px;text-align:right">${stats_recibidas['subtotal']:,.2f}</td></tr>
            <tr><td style="padding:8px">IVA (16%)</td>
              <td style="padding:8px;text-align:right">${stats_emitidas['iva']:,.2f}</td>
              <td style="padding:8px;text-align:right">${stats_recibidas['iva']:,.2f}</td></tr>
            <tr style="background:#FFF9C4;font-weight:bold"><td style="padding:8px">Total</td>
              <td style="padding:8px;text-align:right">${stats_emitidas['total']:,.2f}</td>
              <td style="padding:8px;text-align:right">${stats_recibidas['total']:,.2f}</td></tr>
            <tr style="background:#f8f9fa"><td style="padding:8px">No. de CFDIs</td>
              <td style="padding:8px;text-align:right">{stats_emitidas['count']}</td>
              <td style="padding:8px;text-align:right">{stats_recibidas['count']}</td></tr>
          </tbody>
        </table>
        <h3 style="color:#2E75B6;font-size:14px;border-bottom:2px solid #2E75B6;padding-bottom:4px">Puntos de atencion</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <tbody>{filas_alertas}</tbody>
        </table>
        <p style="color:#888;font-size:11px;margin-top:20px">
          Para cualquier aclaracion, comuniquese con su contador asignado en Sis Rodriguez Contadores Publicos.
          Este reporte fue generado el {fecha_generacion}.
        </p>
      </div>
      <div style="background:#f8f9fa;padding:10px;border-radius:0 0 8px 8px;font-size:11px;color:#888;text-align:center">
        Sis Rodriguez Contadores Publicos · Puebla, Mexico
      </div>
    </div>
    """
