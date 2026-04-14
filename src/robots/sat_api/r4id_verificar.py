# src/robots/r4id_verificar.py
import logging
from sqlite3 import OperationalError

from src.utils.config import settings
from src.utils.db import DB
from src.utils.logging_cfg import setup_logging
from src.services.signer_service import SignerService
from satcfdi.pacs.sat import SAT, EstadoSolicitud

log = logging.getLogger(__name__)

def _as_int(v) -> int:
    try:
        return int(v)
    except Exception:
        try:
            return int(str(v).strip())
        except Exception:
            return -1

def _migrate(db: DB):
    with db.connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS paquetes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_solicitud TEXT,
                id_paquete TEXT UNIQUE,
                estado TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # asegurar columna path_zip para r5/r6
        cols = [row[1] for row in con.execute("PRAGMA table_info(paquetes)")]
        if "path_zip" not in cols:
            try:
                con.execute("ALTER TABLE paquetes ADD COLUMN path_zip TEXT")
                log.info("R4ID: columna 'path_zip' agregada a paquetes")
            except OperationalError:
                pass

def run(id_solicitud: str):
    setup_logging(settings.log_path)
    log.info("R4ID: Verificar estado de solicitud puntual %s", id_solicitud)

    # Cliente SAT
    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    signer = ss.load_signer()
    sat_cli = SAT(signer=signer)

    db = DB(settings.db_path)
    _migrate(db)

    resp = sat_cli.recover_comprobante_status(id_solicitud)
    estado_val = _as_int(resp.get("EstadoSolicitud"))
    paquetes = resp.get("IdsPaquetes", []) or []
    mensaje = resp.get("Mensaje", "")
    cod = resp.get("CodEstatus", "")

    # Actualizar estado en BD y registrar paquetes si hay
    with db.connect() as con:
        con.execute("UPDATE solicitudes SET estado=? WHERE id_solicitud=?", (str(estado_val), id_solicitud))
        if estado_val == _as_int(EstadoSolicitud.TERMINADA):
            for p in paquetes:
                con.execute(
                    "INSERT OR IGNORE INTO paquetes(id_solicitud, id_paquete, estado) VALUES(?,?,?)",
                    (id_solicitud, p, "PENDIENTE"),
                )

    print(f"Solicitud {id_solicitud} -> Estado={estado_val} (CodEstatus={cod}), Mensaje={mensaje}, Paquetes={paquetes}")
