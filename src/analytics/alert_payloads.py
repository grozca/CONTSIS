from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from src.analytics.insights import build_company_month_insights
    from src.analytics.schema import DB_PATH
except ModuleNotFoundError:
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.analytics.insights import build_company_month_insights
    from src.analytics.schema import DB_PATH


def build_alert_payload(
    periodo: str,
    rfc_empresa: str,
    previous_periodo: str | None = None,
    top_n: int = 5,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    insight = build_company_month_insights(
        periodo=periodo,
        rfc_empresa=rfc_empresa,
        previous_periodo=previous_periodo,
        top_n=top_n,
        db_path=db_path,
    )

    empresa = insight["empresa"]
    risk = insight["risk"]
    kpis = insight["kpis"]
    variation = insight["variation"]

    subject = build_subject(empresa["nombre_corto"] or empresa["rfc"], periodo, risk)
    text = build_plain_text(insight)
    html = build_html(insight)

    return {
        "subject": subject,
        "text": text,
        "html": html,
        "metadata": {
            "rfc_empresa": empresa["rfc"],
            "periodo": periodo,
            "risk_level": risk["level"],
            "risk_score": risk["score"],
        },
        "insight": {
            "empresa": empresa,
            "kpis": kpis,
            "variation": variation,
            "risk": risk,
        },
    }


def build_subject(nombre_empresa: str, periodo: str, risk: dict[str, Any]) -> str:
    return f"[{risk['level'].upper()} {risk['score']}] Resumen CFDI {nombre_empresa} {periodo}"


def build_plain_text(insight: dict[str, Any]) -> str:
    empresa = insight["empresa"]
    kpis = insight["kpis"]
    risk = insight["risk"]
    top_clientes = insight["top_clientes"]
    top_proveedores = insight["top_proveedores"]
    variation = insight["variation"]

    lines = [
        f"Resumen ejecutivo CFDI - {empresa['nombre_corto'] or empresa['rfc']}",
        f"RFC: {empresa['rfc']}",
        f"Periodo: {insight['periodo']}",
        f"Riesgo: {risk['level']} ({risk['score']})",
        f"Titular: {risk['headline']}",
        "",
        "KPIs principales:",
        f"- Ingresos: {fmt_currency(kpis['ingresos_mxn'])}",
        f"- Egresos: {fmt_currency(kpis['egresos_mxn'])}",
        f"- CFDI emitidos: {kpis['num_cfdi_emitidos']}",
        f"- CFDI recibidos: {kpis['num_cfdi_recibidos']}",
        f"- Complementos de pago: {kpis['num_pagos']}",
        "",
        "Variaciones:",
        f"- Ingresos vs mes anterior: {fmt_pct_or_na(variation.get('variacion_ingresos_pct'))}",
        f"- Egresos vs mes anterior: {fmt_pct_or_na(variation.get('variacion_egresos_pct'))}",
        f"- Emitidos vs mes anterior: {fmt_pct_or_na(variation.get('variacion_emitidos_pct'))}",
        f"- Recibidos vs mes anterior: {fmt_pct_or_na(variation.get('variacion_recibidos_pct'))}",
        "",
        "Senales:",
    ]

    if risk["signals"]:
        lines.extend(f"- {signal['severity']}: {signal['message']}" for signal in risk["signals"])
    else:
        lines.append("- Sin alertas relevantes")

    lines.extend(
        [
            "",
            "Top clientes:",
            *format_top_lines(top_clientes),
            "",
            "Top proveedores:",
            *format_top_lines(top_proveedores),
        ]
    )

    return "\n".join(lines)


def build_html(insight: dict[str, Any]) -> str:
    empresa = insight["empresa"]
    kpis = insight["kpis"]
    risk = insight["risk"]
    variation = insight["variation"]
    top_clientes = insight["top_clientes"]
    top_proveedores = insight["top_proveedores"]

    signals_html = "".join(
        f"<li><strong>{signal['severity'].upper()}</strong>: {signal['message']}</li>"
        for signal in risk["signals"]
    ) or "<li>Sin alertas relevantes</li>"

    clientes_html = "".join(render_top_row(row) for row in top_clientes) or empty_row("Sin clientes relevantes")
    proveedores_html = "".join(render_top_row(row) for row in top_proveedores) or empty_row("Sin proveedores relevantes")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Resumen CFDI {empresa['rfc']}</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #1f2937; margin: 24px; }}
    .hero {{ background: #f3f4f6; padding: 20px; border-radius: 12px; }}
    .risk-low {{ color: #166534; }}
    .risk-medium {{ color: #b45309; }}
    .risk-high {{ color: #b91c1c; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 12px; margin-top: 16px; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #e5e7eb; }}
    th {{ background: #f9fafb; }}
    h2 {{ margin-top: 28px; }}
  </style>
</head>
<body>
  <div class="hero">
    <h1>Resumen ejecutivo CFDI</h1>
    <p><strong>Empresa:</strong> {empresa['nombre_corto'] or empresa['rfc']}</p>
    <p><strong>RFC:</strong> {empresa['rfc']}</p>
    <p><strong>Periodo:</strong> {insight['periodo']}</p>
    <p class="risk-{risk['level']}"><strong>Riesgo:</strong> {risk['level'].upper()} ({risk['score']})</p>
    <p><strong>Lectura:</strong> {risk['headline']}</p>
  </div>

  <div class="grid">
    <div class="card"><strong>Ingresos</strong><br>{fmt_currency(kpis['ingresos_mxn'])}</div>
    <div class="card"><strong>Egresos</strong><br>{fmt_currency(kpis['egresos_mxn'])}</div>
    <div class="card"><strong>CFDI emitidos</strong><br>{kpis['num_cfdi_emitidos']}</div>
    <div class="card"><strong>CFDI recibidos</strong><br>{kpis['num_cfdi_recibidos']}</div>
    <div class="card"><strong>Complementos de pago</strong><br>{kpis['num_pagos']}</div>
    <div class="card"><strong>Var. ingresos</strong><br>{fmt_pct_or_na(variation.get('variacion_ingresos_pct'))}</div>
  </div>

  <h2>Senales</h2>
  <ul>{signals_html}</ul>

  <h2>Top clientes</h2>
  <table>
    <thead>
      <tr><th>Nombre</th><th>RFC</th><th>CFDI</th><th>Monto MXN</th><th>%</th></tr>
    </thead>
    <tbody>{clientes_html}</tbody>
  </table>

  <h2>Top proveedores</h2>
  <table>
    <thead>
      <tr><th>Nombre</th><th>RFC</th><th>CFDI</th><th>Monto MXN</th><th>%</th></tr>
    </thead>
    <tbody>{proveedores_html}</tbody>
  </table>
</body>
</html>
"""


def render_top_row(row: dict[str, Any]) -> str:
    return (
        "<tr>"
        f"<td>{row['nombre_counterparty']}</td>"
        f"<td>{row['rfc_counterparty']}</td>"
        f"<td>{row['num_cfdi']}</td>"
        f"<td>{fmt_currency(row['monto_total_mxn'])}</td>"
        f"<td>{row['porcentaje_del_total']:.2f}%</td>"
        "</tr>"
    )


def empty_row(message: str) -> str:
    return f"<tr><td colspan='5'>{message}</td></tr>"


def format_top_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- Sin registros"]
    return [
        f"- {row['nombre_counterparty']} ({row['rfc_counterparty']}): {fmt_currency(row['monto_total_mxn'])} [{row['porcentaje_del_total']:.2f}%]"
        for row in rows
    ]


def fmt_currency(value: Any) -> str:
    return f"${float(value or 0):,.2f} MXN"


def fmt_pct_or_na(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):.2f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera payloads de alerta a partir de analytics.")
    parser.add_argument("--yyyy_mm", required=True, help="Periodo a consultar en formato YYYY-MM")
    parser.add_argument("--rfc", required=True, help="RFC de la empresa")
    parser.add_argument("--previous-yyyy_mm", required=False, help="Periodo anterior opcional")
    parser.add_argument("--top-n", type=int, default=5, help="Numero de contrapartes top a incluir")
    parser.add_argument("--format", choices=["json", "text", "html"], default="json")
    parser.add_argument("--db-path", required=False, help="Ruta opcional a analytics.sqlite")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else DB_PATH
    payload = build_alert_payload(
        periodo=args.yyyy_mm,
        rfc_empresa=args.rfc,
        previous_periodo=args.previous_yyyy_mm,
        top_n=args.top_n,
        db_path=db_path,
    )

    if args.format == "text":
        print(payload["text"])
    elif args.format == "html":
        print(payload["html"])
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
