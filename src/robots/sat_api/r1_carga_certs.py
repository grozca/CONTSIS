import logging
from src.utils.config import settings
from src.utils.db import DB
from src.services.signer_service import SignerService
from src.utils.logging_cfg import setup_logging

log = logging.getLogger(__name__)

def run():
    setup_logging(settings.log_path)
    log.info("R1: Carga y verificación de certificados")

    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    info = ss.get_info()
    log.info(f"RFC: {info.rfc}")
    log.info(f"Vigencia: {info.not_before} -> {info.not_after}")

    db = DB(settings.db_path)
    with db.connect() as con:
        con.execute(
            "INSERT INTO cred_status(subject, rfc, not_before, not_after) VALUES(?,?,?,?)",
            (info.subject, info.rfc, info.not_before, info.not_after),
        )
    log.info("R1: Verificación de certificados completada")
