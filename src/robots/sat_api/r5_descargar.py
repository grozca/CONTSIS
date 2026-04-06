# src/robots/r5_descargar.py
import logging
import base64
from pathlib import Path
from src.utils.config import settings
from src.utils.db import DB
from src.utils.logging_cfg import setup_logging
from src.services.signer_service import SignerService
from satcfdi.pacs.sat import SAT

log = logging.getLogger(__name__)

def _ensure_dirs() -> Path:
    boveda = Path(getattr(settings, "boveda_dir", "data/boveda"))
    zip_dir = boveda / "zip"
    zip_dir.mkdir(parents=True, exist_ok=True)
    return zip_dir

def run():
    setup_logging(settings.log_path)
    log.info("R5: Descargar paquetes")

    zip_dir = _ensure_dirs()

    # Cliente SAT
    ss = SignerService(settings.cer_path, settings.key_path, settings.pwd_path)
    signer = ss.load_signer()
    sat_cli = SAT(signer=signer)

    db = DB(settings.db_path)

    # Tomar paquetes pendientes
    with db.connect() as con:
        pendientes = list(con.execute(
            "SELECT id_paquete FROM paquetes WHERE estado='PENDIENTE'"
        ))

    if not pendientes:
        log.info("R5: No hay paquetes pendientes de descarga")
        print("No hay paquetes pendientes de descarga.")
        return

    for (id_paquete,) in pendientes:
        log.info(f"R5: Descargando paquete {id_paquete}")
        resp, paquete_b64 = sat_cli.recover_comprobante_download(id_paquete=id_paquete)
        if not paquete_b64:
            log.warning(f"R5: Paquete vacío {id_paquete}. Resp={resp}")
            continue
        data = base64.b64decode(paquete_b64)
        dest = zip_dir / f"{id_paquete}.zip"
        dest.write_bytes(data)

        with db.connect() as con:
            con.execute(
                "UPDATE paquetes SET estado='DESCARGADO', path_zip=? WHERE id_paquete=?",
                (str(dest), id_paquete),
            )
        log.info(f"R5: Paquete {id_paquete} guardado en {dest}")
        print(f"Descargado: {dest}")
