"""
CONTSIS — Motor de Alertas v1.0
================================
Lee los Excel generados por el robot de CFDIs,
evalúa reglas fiscales y notifica por email y WhatsApp.

Uso:
    python alertas.py                          # revisa todos los Excel en ./data
    python alertas.py --archivo data/xxx.xlsx  # archivo específico
    python alertas.py --piloto                 # modo demo con datos de ejemplo
"""

import os
import sys
import glob
import logging
import argparse
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich import print as rprint

# ── Setup inicial ─────────────────────────────────────────────────────────────
load_dotenv()
console = Console()

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config" / "config.yaml"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"alertas_{date.today()}.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("contsis.alertas")


# ── Carga de configuración ────────────────────────────────────────────────────
def cargar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Carga de datos desde Excel ────────────────────────────────────────────────
def cargar_excel(ruta: str, hoja: str = "CFDI") -> Optional[pd.DataFrame]:
    try:
        df = pd.read_excel(ruta, sheet_name=hoja)
        df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce")
        df["_ARCHIVO"] = Path(ruta).name
        log.info(f"Cargado: {Path(ruta).name} — {len(df)} registros (hoja {hoja})")
        return df
    except Exception as e:
        log.error(f"Error cargando {ruta}: {e}")
        return None


def cargar_todos_los_excel(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    carpeta = Path(cfg["datos"]["carpeta_excel"])
    patron_e = cfg["datos"]["patron_emitidas"]
    patron_r = cfg["datos"]["patron_recibidas"]

    archivos_e = sorted(carpeta.glob(patron_e))
    archivos_r = sorted(carpeta.glob(patron_r))

    frames_e = [cargar_excel(str(f)) for f in archivos_e]
    frames_r = [cargar_excel(str(f)) for f in archivos_r]

    df_e = pd.concat([f for f in frames_e if f is not None], ignore_index=True) if frames_e else pd.DataFrame()
    df_r = pd.concat([f for f in frames_r if f is not None], ignore_index=True) if frames_r else pd.DataFrame()

    return df_e, df_r


# ── Estructura de alerta ──────────────────────────────────────────────────────
def crear_alerta(regla: str, severidad: str, titulo: str, detalle: str,
                 monto: float = 0, rfc: str = "", nombre: str = "",
                 uuid: str = "", fecha: str = "") -> dict:
    return {
        "timestamp": datetime.now().isoformat(),
        "regla": regla,
        "severidad": severidad,        # ALTA / MEDIA / BAJA
        "titulo": titulo,
        "detalle": detalle,
        "monto_mxn": monto,
        "rfc": rfc,
        "nombre": nombre,
        "uuid": uuid,
        "fecha_cfdi": fecha,
    }


# ── REGLAS DE ALERTA ──────────────────────────────────────────────────────────

def regla_ingreso_alto(df: pd.DataFrame, cfg: dict) -> list[dict]:
    """R1: Ingreso único > umbral configurable."""
    alertas = []
    rcfg = cfg["reglas"]["ingreso_alto"]
    if not rcfg["habilitado"]:
        return alertas

    umbral = rcfg["umbral_mxn"]
    ingresos = df[
        (df["TIPO_COMPROB"].isin(rcfg["tipos_comprob"])) &
        (df["SUBTOTAL_MXN"] > umbral)
    ]

    for _, row in ingresos.iterrows():
        alertas.append(crear_alerta(
            regla="INGRESO_ALTO",
            severidad=rcfg["severidad"],
            titulo=f"Ingreso inusual: ${row['SUBTOTAL_MXN']:,.0f} MXN",
            detalle=(
                f"Se recibió un CFDI de ingreso por ${row['SUBTOTAL_MXN']:,.2f} MXN "
                f"de {row['RECEPTOR_NOMBRE']} (RFC: {row['RFC_RECEPTOR']}) "
                f"el {row['FECHA'].strftime('%d/%m/%Y') if pd.notna(row['FECHA']) else 'N/D'}. "
                f"Supera el umbral configurado de ${umbral:,.0f} MXN. "
                f"Verificar que el origen del ingreso esté correctamente clasificado ante el SAT."
            ),
            monto=row["SUBTOTAL_MXN"],
            rfc=row.get("RFC_RECEPTOR", ""),
            nombre=row.get("RECEPTOR_NOMBRE", ""),
            uuid=row.get("UUID", ""),
            fecha=str(row["FECHA"].date()) if pd.notna(row["FECHA"]) else "",
        ))

    return alertas


def regla_concentracion_cliente(df: pd.DataFrame, cfg: dict) -> list[dict]:
    """R5: Un solo cliente concentra más del X% del ingreso mensual."""
    alertas = []
    rcfg = cfg["reglas"]["concentracion_cliente"]
    if not rcfg["habilitado"]:
        return alertas

    ingresos = df[df["TIPO_COMPROB"] == "I"].copy()
    if ingresos.empty:
        return alertas

    total_mes = ingresos["SUBTOTAL_MXN"].sum()
    if total_mes == 0:
        return alertas

    por_cliente = ingresos.groupby("RECEPTOR_NOMBRE")["SUBTOTAL_MXN"].sum()
    pct_maximo = rcfg["porcentaje_maximo"]

    for cliente, monto in por_cliente.items():
        pct = (monto / total_mes) * 100
        if pct > pct_maximo:
            rfc_cliente = ingresos[ingresos["RECEPTOR_NOMBRE"] == cliente]["RFC_RECEPTOR"].iloc[0]
            alertas.append(crear_alerta(
                regla="CONCENTRACION_CLIENTE",
                severidad=rcfg["severidad"],
                titulo=f"Concentración de ingresos: {cliente} = {pct:.1f}%",
                detalle=(
                    f"{cliente} representa el {pct:.1f}% del ingreso total del período "
                    f"(${monto:,.2f} de ${total_mes:,.2f} MXN). "
                    f"Alta dependencia de un solo cliente. RFC: {rfc_cliente}."
                ),
                monto=monto,
                rfc=rfc_cliente,
                nombre=str(cliente),
            ))

    return alertas


def regla_tipo_cambio_anomalo(df: pd.DataFrame, cfg: dict) -> list[dict]:
    """R6: CFDIs en USD con tipo de cambio fuera del rango esperado."""
    alertas = []
    rcfg = cfg["reglas"]["tipo_cambio_anomalo"]
    if not rcfg["habilitado"]:
        return alertas

    usd = df[
        (df["MONEDA"] == "USD") &
        (df["TIPO_CAMBIO"] > 0) &
        (
            (df["TIPO_CAMBIO"] < rcfg["rango_minimo"]) |
            (df["TIPO_CAMBIO"] > rcfg["rango_maximo"])
        )
    ]

    for _, row in usd.iterrows():
        alertas.append(crear_alerta(
            regla="TIPO_CAMBIO_ANOMALO",
            severidad=rcfg["severidad"],
            titulo=f"Tipo de cambio fuera de rango: ${row['TIPO_CAMBIO']:.4f}",
            detalle=(
                f"CFDI UUID {row['UUID'][:8]}... usa tipo de cambio ${row['TIPO_CAMBIO']:.4f} "
                f"(rango esperado: ${rcfg['rango_minimo']:.2f} – ${rcfg['rango_maximo']:.2f}). "
                f"Monto: ${row['SUBTOTAL']:,.2f} USD = ${row['SUBTOTAL_MXN']:,.2f} MXN. "
                f"Verificar tipo de cambio publicado por Banco de México en esa fecha."
            ),
            monto=row["SUBTOTAL_MXN"],
            uuid=row.get("UUID", ""),
            rfc=row.get("RFC_EMISOR", ""),
            nombre=row.get("EMISOR_NOMBRE", ""),
            fecha=str(row["FECHA"].date()) if pd.notna(row["FECHA"]) else "",
        ))

    return alertas


def regla_pago_sin_clasificar(df_emitidas: pd.DataFrame, cfg: dict) -> list[dict]:
    """R4: CFDIs tipo P (pago) — verificar que correspondan a facturas previas."""
    alertas = []
    rcfg = cfg["reglas"]["pago_sin_ingreso"]
    if not rcfg["habilitado"]:
        return alertas

    pagos = df_emitidas[df_emitidas["TIPO_COMPROB"] == "P"]
    ingresos_rfcs = set(df_emitidas[df_emitidas["TIPO_COMPROB"] == "I"]["RFC_RECEPTOR"].unique())

    for _, row in pagos.iterrows():
        if row["RFC_RECEPTOR"] not in ingresos_rfcs:
            alertas.append(crear_alerta(
                regla="PAGO_SIN_INGRESO_RELACIONADO",
                severidad=rcfg["severidad"],
                titulo=f"Complemento de pago sin factura de ingreso previa",
                detalle=(
                    f"Se emitió complemento de pago (UUID: {row['UUID'][:8]}...) "
                    f"para {row['RECEPTOR_NOMBRE']} (RFC: {row['RFC_RECEPTOR']}) "
                    f"pero no existe CFDI de ingreso (tipo I) previo para ese RFC en el período. "
                    f"Revisar si la factura original está en un período anterior."
                ),
                rfc=row.get("RFC_RECEPTOR", ""),
                nombre=row.get("RECEPTOR_NOMBRE", ""),
                uuid=row.get("UUID", ""),
                fecha=str(row["FECHA"].date()) if pd.notna(row["FECHA"]) else "",
            ))

    return alertas


def regla_vencimientos_sat(cfg: dict) -> list[dict]:
    """R7: Recordatorios de fechas fiscales importantes del SAT."""
    alertas = []
    rcfg = cfg["reglas"]["vencimientos_sat"]
    if not rcfg["habilitado"]:
        return alertas

    hoy = date.today()
    mes_actual = hoy.month
    anio_actual = hoy.year
    dias_ant = rcfg["dias_anticipacion"]

    # Fechas clave SAT México (régimen general)
    vencimientos = [
        {
            "nombre": "Declaración mensual ISR e IVA",
            "fecha": date(anio_actual, mes_actual, 17),
            "descripcion": f"Vence la declaración mensual de ISR e IVA correspondiente al mes anterior."
        },
        {
            "nombre": "DIOT mensual",
            "fecha": date(anio_actual, mes_actual, 17),
            "descripcion": "Vence la Declaración Informativa de Operaciones con Terceros (DIOT)."
        },
    ]

    for v in vencimientos:
        dias_restantes = (v["fecha"] - hoy).days
        if 0 <= dias_restantes <= dias_ant:
            alertas.append(crear_alerta(
                regla="VENCIMIENTO_SAT",
                severidad="ALTA" if dias_restantes <= 2 else "MEDIA",
                titulo=f"Vence en {dias_restantes} día(s): {v['nombre']}",
                detalle=f"{v['descripcion']} Fecha límite: {v['fecha'].strftime('%d/%m/%Y')}.",
            ))

    return alertas


# ── EVALUADOR PRINCIPAL ───────────────────────────────────────────────────────
def evaluar_todas_las_reglas(df_emitidas: pd.DataFrame,
                              df_recibidas: pd.DataFrame,
                              cfg: dict) -> list[dict]:
    alertas = []

    log.info("Evaluando reglas de alerta...")

    if not df_emitidas.empty:
        alertas += regla_ingreso_alto(df_emitidas, cfg)
        alertas += regla_concentracion_cliente(df_emitidas, cfg)
        alertas += regla_tipo_cambio_anomalo(df_emitidas, cfg)
        alertas += regla_pago_sin_clasificar(df_emitidas, cfg)

    alertas += regla_vencimientos_sat(cfg)

    # Ordenar por severidad
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    alertas.sort(key=lambda a: orden.get(a["severidad"], 99))

    log.info(f"Total alertas generadas: {len(alertas)}")
    return alertas


# ── NOTIFICACIONES ────────────────────────────────────────────────────────────
def formatear_mensaje_whatsapp(alertas: list[dict], empresa: str) -> str:
    if not alertas:
        return f"✅ *CONTSIS* — {empresa}\nRevisión completada. No se encontraron alertas."

    altas = [a for a in alertas if a["severidad"] == "ALTA"]
    medias = [a for a in alertas if a["severidad"] == "MEDIA"]
    bajas = [a for a in alertas if a["severidad"] == "BAJA"]

    lineas = [
        f"⚠️ *CONTSIS ALERTAS* — {empresa}",
        f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"{'─'*35}",
    ]

    if altas:
        lineas.append(f"\n🔴 *ALTA PRIORIDAD ({len(altas)})*")
        for a in altas[:3]:  # máximo 3 en WhatsApp para no saturar
            lineas.append(f"• {a['titulo']}")
            if a["monto_mxn"] > 0:
                lineas.append(f"  Monto: ${a['monto_mxn']:,.0f} MXN")

    if medias:
        lineas.append(f"\n🟡 *MEDIA PRIORIDAD ({len(medias)})*")
        for a in medias[:2]:
            lineas.append(f"• {a['titulo']}")

    if bajas:
        lineas.append(f"\n🟢 *BAJA PRIORIDAD ({len(bajas)})*")
        for a in bajas[:2]:
            lineas.append(f"• {a['titulo']}")

    lineas.append(f"\n{'─'*35}")
    lineas.append("Ver reporte completo en el sistema CONTSIS.")

    return "\n".join(lineas)


def enviar_whatsapp(mensaje: str, cfg: dict) -> bool:
    wcfg = cfg["notificaciones"]["whatsapp"]
    if not wcfg["habilitado"]:
        return False

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", wcfg.get("numero_origen", ""))
    to_numbers_str = os.getenv("TWILIO_WHATSAPP_TO", "")
    to_numbers = [n.strip() for n in to_numbers_str.split(",") if n.strip()]

    if not all([account_sid, auth_token, from_number, to_numbers]):
        log.warning("WhatsApp no configurado — faltan credenciales Twilio en .env")
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        for to in to_numbers:
            client.messages.create(body=mensaje, from_=from_number, to=to)
            log.info(f"WhatsApp enviado a {to}")
        return True
    except ImportError:
        log.error("Twilio no instalado. Ejecuta: pip install twilio")
        return False
    except Exception as e:
        log.error(f"Error enviando WhatsApp: {e}")
        return False


def formatear_email_html(alertas: list[dict], empresa: str, cfg: dict) -> tuple[str, str]:
    """Retorna (asunto, cuerpo_html)."""
    altas = [a for a in alertas if a["severidad"] == "ALTA"]
    medias = [a for a in alertas if a["severidad"] == "MEDIA"]
    bajas = [a for a in alertas if a["severidad"] == "BAJA"]

    if not alertas:
        asunto = f"{cfg['notificaciones']['email']['asunto_prefijo']} Sin novedades — {empresa}"
        html = f"<p>Revisión completada para <b>{empresa}</b>. No se detectaron alertas.</p>"
        return asunto, html

    n_altas = len(altas)
    asunto = (
        f"{cfg['notificaciones']['email']['asunto_prefijo']} "
        f"{'🔴 ' + str(n_altas) + ' alertas urgentes' if n_altas else '🟡 Alertas pendientes'} "
        f"— {empresa} — {datetime.now().strftime('%d/%m/%Y')}"
    )

    def badge(sev):
        colores = {"ALTA": "#dc3545", "MEDIA": "#fd7e14", "BAJA": "#198754"}
        return f'<span style="background:{colores.get(sev,"#6c757d")};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold">{sev}</span>'

    filas_html = ""
    for a in alertas:
        filas_html += f"""
        <tr style="border-bottom:1px solid #dee2e6">
          <td style="padding:10px 8px">{badge(a['severidad'])}</td>
          <td style="padding:10px 8px"><b>{a['titulo']}</b><br>
            <small style="color:#6c757d">{a['detalle']}</small></td>
          <td style="padding:10px 8px;text-align:right">
            {'${:,.0f}'.format(a['monto_mxn']) if a['monto_mxn'] > 0 else '—'}
          </td>
          <td style="padding:10px 8px;color:#6c757d;font-size:13px">{a.get('fecha_cfdi','') or a['timestamp'][:10]}</td>
        </tr>"""

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:800px;margin:0 auto">
      <div style="background:#1a1a2e;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">⚠️ CONTSIS — Sistema de Alertas</h2>
        <p style="margin:4px 0 0;opacity:0.8">{empresa} · {datetime.now().strftime('%d de %B de %Y, %H:%M')}</p>
      </div>

      <div style="background:#f8f9fa;padding:16px;display:flex;gap:16px">
        <div style="background:white;border-left:4px solid #dc3545;padding:12px 20px;border-radius:4px">
          <div style="font-size:28px;font-weight:bold;color:#dc3545">{len(altas)}</div>
          <div style="font-size:12px;color:#6c757d">ALTA</div>
        </div>
        <div style="background:white;border-left:4px solid #fd7e14;padding:12px 20px;border-radius:4px">
          <div style="font-size:28px;font-weight:bold;color:#fd7e14">{len(medias)}</div>
          <div style="font-size:12px;color:#6c757d">MEDIA</div>
        </div>
        <div style="background:white;border-left:4px solid #198754;padding:12px 20px;border-radius:4px">
          <div style="font-size:28px;font-weight:bold;color:#198754">{len(bajas)}</div>
          <div style="font-size:12px;color:#6c757d">BAJA</div>
        </div>
      </div>

      <table style="width:100%;border-collapse:collapse;background:white">
        <thead>
          <tr style="background:#f1f3f5;font-size:13px;color:#6c757d">
            <th style="padding:10px 8px;text-align:left;width:90px">SEVERIDAD</th>
            <th style="padding:10px 8px;text-align:left">ALERTA</th>
            <th style="padding:10px 8px;text-align:right;width:130px">MONTO MXN</th>
            <th style="padding:10px 8px;text-align:left;width:100px">FECHA</th>
          </tr>
        </thead>
        <tbody>{filas_html}</tbody>
      </table>

      <div style="background:#f8f9fa;padding:12px;border-radius:0 0 8px 8px;font-size:12px;color:#6c757d;text-align:center">
        CONTSIS v1.0 · Generado automáticamente · No responder a este correo
      </div>
    </div>
    """

    return asunto, html


def enviar_email(alertas: list[dict], cfg: dict) -> bool:
    ecfg = cfg["notificaciones"]["email"]
    if not ecfg["habilitado"]:
        return False

    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    remitente = os.getenv("EMAIL_REMITENTE", ecfg.get("remitente", ""))
    password = os.getenv("EMAIL_PASSWORD", "")
    destinatarios_str = os.getenv("EMAIL_DESTINATARIOS", "")
    destinatarios = [d.strip() for d in destinatarios_str.split(",") if d.strip()]
    if not destinatarios:
        destinatarios = ecfg.get("destinatarios", [])

    if not all([remitente, password, destinatarios]):
        log.warning("Email no configurado — faltan credenciales en .env")
        return False

    empresa = cfg["empresa"]["nombre"]
    asunto, cuerpo_html = formatear_email_html(alertas, empresa, cfg)

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = asunto
        msg["From"] = f"CONTSIS <{remitente}>"
        msg["To"] = ", ".join(destinatarios)
        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

        with smtplib.SMTP(ecfg["smtp_server"], ecfg["smtp_port"]) as server:
            server.starttls()
            server.login(remitente, password)
            server.sendmail(remitente, destinatarios, msg.as_string())

        log.info(f"Email enviado a: {', '.join(destinatarios)}")
        return True
    except Exception as e:
        log.error(f"Error enviando email: {e}")
        return False


# ── REPORTE EXCEL ─────────────────────────────────────────────────────────────
def generar_reporte_excel(alertas: list[dict], cfg: dict) -> Path:
    carpeta = Path(cfg["reportes"]["carpeta_salida"])
    carpeta.mkdir(exist_ok=True)
    nombre = f"alertas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    ruta = carpeta / nombre

    df = pd.DataFrame(alertas)
    if df.empty:
        df = pd.DataFrame(columns=["timestamp","regla","severidad","titulo","detalle","monto_mxn","rfc","nombre","uuid","fecha_cfdi"])

    with pd.ExcelWriter(ruta, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Alertas")
        ws = writer.sheets["Alertas"]
        # Anchos
        for i, col in enumerate(df.columns, 1):
            ws.column_dimensions[ws.cell(1, i).column_letter].width = max(len(str(col)) + 4, 20)

    log.info(f"Reporte Excel guardado: {ruta}")
    return ruta


# ── DISPLAY EN CONSOLA ────────────────────────────────────────────────────────
def mostrar_resumen_consola(alertas: list[dict]):
    if not alertas:
        rprint("\n[bold green]✅ Sin alertas detectadas.[/bold green]\n")
        return

    tabla = Table(title=f"CONTSIS — Alertas ({len(alertas)} total)", show_header=True, header_style="bold white on dark_blue")
    tabla.add_column("Severidad", width=10)
    tabla.add_column("Regla", width=28)
    tabla.add_column("Título", width=45)
    tabla.add_column("Monto MXN", justify="right", width=15)

    colores = {"ALTA": "red", "MEDIA": "yellow", "BAJA": "green"}

    for a in alertas:
        color = colores.get(a["severidad"], "white")
        tabla.add_row(
            f"[{color}]{a['severidad']}[/{color}]",
            a["regla"],
            a["titulo"][:44],
            f"${a['monto_mxn']:,.0f}" if a["monto_mxn"] > 0 else "—",
        )

    console.print(tabla)


# ── PUNTO DE ENTRADA ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="CONTSIS Motor de Alertas")
    parser.add_argument("--archivo", help="Ruta a archivo Excel específico (emitidas)")
    parser.add_argument("--piloto", action="store_true", help="Modo piloto: muestra alertas sin enviar notificaciones")
    parser.add_argument("--solo-consola", action="store_true", help="No enviar notificaciones, solo mostrar en pantalla")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("CONTSIS Motor de Alertas — Iniciando")
    log.info("=" * 60)

    cfg = cargar_config()
    empresa = cfg["empresa"]["nombre"]

    # Carga de datos
    if args.archivo:
        df_e = cargar_excel(args.archivo)
        df_r = pd.DataFrame()
        if df_e is None:
            log.error("No se pudo cargar el archivo.")
            sys.exit(1)
    else:
        df_e, df_r = cargar_todos_los_excel(cfg)

    if df_e.empty and df_r.empty:
        log.warning("No se encontraron archivos Excel en la carpeta configurada.")
        log.info(f"Carpeta buscada: {cfg['datos']['carpeta_excel']}")
        sys.exit(0)

    # Evaluación de reglas
    alertas = evaluar_todas_las_reglas(df_e, df_r, cfg)

    # Mostrar en consola siempre
    mostrar_resumen_consola(alertas)

    # Generar reporte Excel
    if cfg["reportes"]["generar_excel"]:
        reporte_path = generar_reporte_excel(alertas, cfg)
        log.info(f"Reporte: {reporte_path}")

    # Notificaciones (solo si no es modo piloto o solo-consola)
    if not args.piloto and not args.solo_consola and alertas:
        log.info("Enviando notificaciones...")

        # Email
        enviar_email(alertas, cfg)

        # WhatsApp
        msg_wa = formatear_mensaje_whatsapp(alertas, empresa)
        enviar_whatsapp(msg_wa, cfg)

    elif args.piloto:
        log.info("Modo piloto — notificaciones deshabilitadas")
        console.print("\n[dim]Mensaje WhatsApp que se enviaría:[/dim]")
        msg_wa = formatear_mensaje_whatsapp(alertas, empresa)
        console.print(f"[dim]{msg_wa}[/dim]\n")

    log.info("Motor de alertas finalizado.")


if __name__ == "__main__":
    main()