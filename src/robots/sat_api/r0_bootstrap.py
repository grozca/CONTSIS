from pathlib import Path
import logging
from src.utils.config import settings
from src.utils.db import DB
from src.utils.logging_cfg import setup_logging

log = logging.getLogger(__name__)

def run():
    setup_logging(settings.log_path)
    log.info("R0: Bootstrap iniciado")

    # Verificación de archivos de credenciales
    for p in [settings.cer_path, settings.key_path, settings.pwd_path]:
        if not Path(p).is_file():
            log.error(f"Archivo faltante: {p}")
            raise FileNotFoundError(f"Falta archivo requerido: {p}")
        log.info(f"OK archivo: {p}")

    # DB mínima
    db = DB(settings.db_path)
    db.migrate_min()
    with db.connect() as con:
        con.execute(
            "INSERT INTO health(check_name, status, details) VALUES(?,?,?)",
            ("bootstrap", "ok", "archivos y db verificados"),
        )
    log.info("R0: Bootstrap finalizado correctamente")
