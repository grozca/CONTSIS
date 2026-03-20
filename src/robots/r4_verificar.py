# src/robots/r4_verificar.py
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

def _migrate_r4(db: DB):
    """Crea la tabla paquetes si no existe y asegura la columna path_zip."""
    with db.connect() as con:
        con.executescript(SQL_CREATE_PAQUETES)
        # Asegura columna path_zip (SQLite no tiene IF NOT EXISTS para columnas)
        cols = [row[1] for row in con.execute("PRAGMA table_info(paquetes)")]
        if "path_zip" not in cols:
            try:
                con.execute("ALTER TABLE paquetes ADD COLUMN path_zip TEXT")
                log.info("R4: columna 'path_zip' agregada a paquetes")
            except OperationalError:
                # Si por alguna razón ya existe o falla, seguimos
                pass

def _int_estado(value) -> int:
    """Normaliza EstadoSolicitud a int (acepta enum/int/str)."""
    try:
        # Si viene como enum, castear a int
        return int(value)
    except Exception:
        try:
            return int(str(value).strip())
        except Exception:
            return -1

def _cfg_int(name: str, default: int) -> int:
    try:
        return int(getattr(settings, name, default))
    except Exception:
        return default

def run():
    setup_logging(settings.log_path)
    log.info("R4: Verificar estado de solicitudes (con reintentos)")

    max_reintentos = _cfg_int("max_reintentos", 6)
    espera = _cfg_int("segundos_espera", 30)

    # Cliente SAT
    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    signer = ss.load_signer()
    sat_cli = SAT(signer=signer)

    db = DB(settings.db_path)
    _migrate_r4(db)

    # Solicitudes con estado SOLICITADA
    with db.connect() as con:
        pendientes = [row[0] for row in con.execute(
            "SELECT id_solicitud FROM solicitudes WHERE estado='SOLICITADA'"
        )]

    if not pendientes:
        log.info("R4: No hay solicitudes pendientes")
        print("No hay solicitudes pendientes.")
        return

    for id_solicitud in pendientes:
        intento = 0
        while True:
            intento += 1
            log.info(f"R4: Consultando estado de {id_solicitud} (intento {intento}/{max_reintentos})")
            resp = sat_cli.recover_comprobante_status(id_solicitud)

            estado_val = _int_estado(resp.get("EstadoSolicitud"))
            paquetes = resp.get("IdsPaquetes", []) or []
            cod = resp.get("CodEstatus", "")
            msg = resp.get("Mensaje", "")

            if estado_val == _int_estado(EstadoSolicitud.TERMINADA):
                log.info(f"R4: {id_solicitud} TERMINADA. Paquetes={len(paquetes)}")
                with db.connect() as con:
                    con.execute("UPDATE solicitudes SET estado='TERMINADA' WHERE id_solicitud=?", (id_solicitud,))
                    for p in paquetes:
                        con.execute(
                            "INSERT OR IGNORE INTO paquetes(id_solicitud, id_paquete, estado) VALUES(?,?,?)",
                            (id_solicitud, p, "PENDIENTE"),
                        )
                print(f"Solicitud {id_solicitud} TERMINADA. Paquetes: {paquetes}")
                break

            if estado_val == _int_estado(EstadoSolicitud.EN_PROCESO):
                log.info(f"R4: {id_solicitud} EN_PROCESO (CodEstatus={cod}). Esperando {espera}s…")
                if intento >= max_reintentos:
                    print(f"Solicitud {id_solicitud} sigue EN_PROCESO después de {max_reintentos} intentos.")
                    break
                time.sleep(espera)
                continue

            # Otros estados (rechazada, error, etc.)
            log.warning(f"R4: {id_solicitud} estado {estado_val} (CodEstatus={cod}). Resp={resp}")
            print(f"Solicitud {id_solicitud} en estado {estado_val}. Mensaje: {msg}")
            break
