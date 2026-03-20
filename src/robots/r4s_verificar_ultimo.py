# src/robots/r4s_verificar_ultimo.py
import logging
import time
from sqlite3 import OperationalError

from src.utils.config import settings
from src.utils.db import DB
from src.utils.logging_cfg import setup_logging
from src.services.signer_service import SignerService
from satcfdi.pacs.sat import SAT, EstadoSolicitud

log = logging.getLogger(__name__)

SQL_CREATE_PAQUETES = """
CREATE TABLE IF NOT EXISTS paquetes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_solicitud TEXT,
    id_paquete TEXT UNIQUE,
    estado TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

def _migrate(db: DB):
    with db.connect() as con:
        con.executescript(SQL_CREATE_PAQUETES)
        cols = [row[1] for row in con.execute("PRAGMA table_info(paquetes)")]
        if "path_zip" not in cols:
            try:
                con.execute("ALTER TABLE paquetes ADD COLUMN path_zip TEXT")
                log.info("R4S: columna 'path_zip' agregada a paquetes")
            except OperationalError:
                pass

def _as_int(v) -> int:
    try:
        return int(v)
    except Exception:
        try:
            return int(str(v).strip())
        except Exception:
            return -1

def _cfg_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except Exception:
        return default

def run():
    setup_logging(settings.log_path)
    log.info("R4S: Verificar SOLO la última solicitud SOLICITADA (con reintentos)")

    max_reintentos = _cfg_int("max_reintentos", 20)   # un poco más agresivo por si acaso
    espera = _cfg_int("segundos_espera", 60)

    # Cliente SAT
    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    signer = ss.load_signer()
    sat_cli = SAT(signer=signer)

    db = DB(settings.db_path)
    _migrate(db)

    # Tomar SOLO la última solicitud SOLICITADA (por ID desc)
    with db.connect() as con:
        row = con.execute(
            "SELECT id_solicitud FROM solicitudes WHERE estado='SOLICITADA' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        log.info("R4S: No hay solicitudes con estado SOLICITADA")
        print("No hay solicitudes SOLICITADA para verificar.")
        return

    id_solicitud = row[0]
    log.info(f"R4S: Verificando la más reciente -> {id_solicitud}")

    intento = 0
    while True:
        intento += 1
        log.info(f"R4S: Consultando estado de {id_solicitud} (intento {intento}/{max_reintentos})")
        resp = sat_cli.recover_comprobante_status(id_solicitud)

        estado_val = _as_int(resp.get("EstadoSolicitud"))
        paquetes = resp.get("IdsPaquetes", []) or []
        cod = resp.get("CodEstatus", "")
        msg = resp.get("Mensaje", "")

        if estado_val == _as_int(EstadoSolicitud.TERMINADA):
            log.info(f"R4S: {id_solicitud} TERMINADA. Paquetes={len(paquetes)}")
            with db.connect() as con:
                con.execute("UPDATE solicitudes SET estado='TERMINADA' WHERE id_solicitud=?", (id_solicitud,))
                for p in paquetes:
                    con.execute(
                        "INSERT OR IGNORE INTO paquetes(id_solicitud, id_paquete, estado) VALUES(?,?,?)",
                        (id_solicitud, p, "PENDIENTE"),
                    )
            print(f"TERMINADA. Paquetes: {paquetes}")
            break

        if estado_val == _as_int(EstadoSolicitud.EN_PROCESO):
            log.info(f"R4S: {id_solicitud} EN_PROCESO (CodEstatus={cod}). Esperando {espera}s…")
            if intento >= max_reintentos:
                print(f"Sigue EN_PROCESO después de {max_reintentos} intentos. Mensaje: {msg}")
                break
            time.sleep(espera)
            continue

        # Otros estados (rechazada, error, etc.)
        log.warning(f"R4S: {id_solicitud} estado {estado_val} (CodEstatus={cod}). Resp={resp}")
        print(f"Estado {estado_val}. Mensaje: {msg}")
        break
