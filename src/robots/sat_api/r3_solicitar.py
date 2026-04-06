# src/robots/r3_solicitar.py
import logging
from datetime import date, timedelta

from satcfdi.pacs.sat import (
    SAT,
    TipoDescargaMasivaTerceros,
    EstadoComprobante,
)

from src.utils.config import settings
from src.utils.db import DB
from src.utils.logging_cfg import setup_logging
from src.services.signer_service import SignerService

log = logging.getLogger(__name__)

SQL_CREATE_SOLICITUDES = """
CREATE TABLE IF NOT EXISTS solicitudes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rfc TEXT,
    tipo TEXT,
    modo TEXT,
    fecha_ini TEXT,
    fecha_fin TEXT,
    id_solicitud TEXT UNIQUE,
    estado TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def _migrate_r3(db: DB) -> None:
    with db.connect() as con:
        con.executescript(SQL_CREATE_SOLICITUDES)

def _fechas_resueltas():
    # Si vienen ambas fechas en .env, úsalas; si no, últimos 30 días
    if settings.fecha_ini and settings.fecha_fin:
        y1, m1, d1 = map(int, settings.fecha_ini.split("-"))
        y2, m2, d2 = map(int, settings.fecha_fin.split("-"))
        return date(y1, m1, d1), date(y2, m2, d2)
    fin = date.today()
    ini = fin - timedelta(days=30)
    return ini, fin

def run():
    setup_logging(settings.log_path)
    log.info("R3: Solicitar Descarga Masiva (satcfdi)")

    # Cargar firmante y resolver RFC
    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    signer = ss.load_signer()
    rfc = (getattr(settings, "rfc", "") or getattr(signer, "rfc", "")).strip()
    if not rfc:
        raise ValueError("No se pudo resolver el RFC (ni en .env ni en el certificado).")

    # Fechas normalizadas
    f_ini, f_fin = _fechas_resueltas()
    if f_fin < f_ini:
        f_ini, f_fin = f_fin, f_ini

    # Parámetros de solicitud
    tipo = (settings.tipo_solicitud or "CFDI").upper()
    modo = (settings.modo or "RECIBIDAS").upper()
    tipo_req = TipoDescargaMasivaTerceros.CFDI if tipo == "CFDI" else TipoDescargaMasivaTerceros.RETENCIONES

    sat_cli = SAT(signer=signer)
    log.info(f"R3: modo={modo}, tipo={tipo}, rfc_en_uso={rfc}, rango={f_ini}..{f_fin}")

    # Llamadas correctas por modo:
    if modo == "EMITIDAS":
        # Para EMITIDAS el RFC del solicitante va como EMISOR
        resp = sat_cli.recover_comprobante_emitted_request(
            fecha_inicial=f_ini,
            fecha_final=f_fin,
            rfc_emisor=rfc,
            tipo_solicitud=tipo_req,
        )
    else:
        # RECIBIDAS requiere especificar explícitamente VIGENTE
        resp = sat_cli.recover_comprobante_received_request(
            fecha_inicial=f_ini,
            fecha_final=f_fin,
            rfc_receptor=rfc,
            tipo_solicitud=tipo_req,
            estado_comprobante=EstadoComprobante.VIGENTE,  # clave para evitar 301 por cancelados
        )

    id_solicitud = resp.get("IdSolicitud")
    if not id_solicitud:
        raise RuntimeError(f"SAT no devolvió IdSolicitud. Respuesta: {resp}")

    # Persistir en DB
    db = DB(settings.db_path)
    _migrate_r3(db)
    with db.connect() as con:
        con.execute(
            """
            INSERT OR IGNORE INTO solicitudes
                (rfc, tipo, modo, fecha_ini, fecha_fin, id_solicitud, estado)
            VALUES (?,?,?,?,?,?,?)
            """,
            (rfc, tipo, modo, f_ini.isoformat(), f_fin.isoformat(), id_solicitud, "SOLICITADA"),
        )

    log.info(f"R3: Solicitud creada. IdSolicitud={id_solicitud}")
    print(f"IdSolicitud: {id_solicitud}")
