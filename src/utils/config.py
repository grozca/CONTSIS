# src/utils/config.py
from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    cer_path: Path = Path(os.getenv("SAT_CER_PATH", "data/csd/cert.cer"))
    key_path: Path = Path(os.getenv("SAT_KEY_PATH", "data/csd/key.key"))
    pwd_path: Path = Path(os.getenv("SAT_PWD_PATH", "data/csd/password.txt"))

    # Infraestructura
    log_path: Path = Path(os.getenv("LOG_PATH", "logs/app.log"))
    db_path: Path = Path(os.getenv("DB_PATH", "data/db/conta_sat.sqlite"))

    # Carpetas base
    @property
    def boveda_dir(self) -> Path:
        return Path(os.getenv("BOVEDA_DIR", "data/boveda"))

    # Parámetros de solicitudes SAT
    rfc: str = os.getenv("SAT_RFC", "").strip()
    tipo_solicitud: str = os.getenv("SAT_TIPO_SOLICITUD", "CFDI").strip()   # CFDI | RETENCIONES
    modo: str = os.getenv("SAT_MODO", "RECIBIDAS").strip()                  # RECIBIDAS | EMITIDAS
    fecha_ini: str = os.getenv("SAT_FECHA_INI", "").strip()                 # YYYY-MM-DD
    fecha_fin: str = os.getenv("SAT_FECHA_FIN", "").strip()                 # YYYY-MM-DD

settings = Settings()
