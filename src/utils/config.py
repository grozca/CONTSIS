# src/utils/config.py
from dataclasses import dataclass, field
from pathlib import Path
import os

from runtime_paths import (
    asset_path,
    config_path,
    data_path,
    get_runtime_setting,
    load_project_env,
    log_path as runtime_log_path,
    preferred_env_path,
    runtime_root,
)


load_project_env()


def _resolve_env_path(env_name: str, default_path: Path) -> Path:
    raw_value = os.getenv(env_name, "").strip() or get_runtime_setting(env_name)
    if not raw_value:
        return default_path

    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate
    return (runtime_root() / candidate).resolve()


@dataclass
class Settings:
    cer_path: Path = field(default_factory=lambda: _resolve_env_path("SAT_CER_PATH", data_path("csd", "cert.cer")))
    key_path: Path = field(default_factory=lambda: _resolve_env_path("SAT_KEY_PATH", data_path("csd", "key.key")))
    pwd_path: Path = field(default_factory=lambda: _resolve_env_path("SAT_PWD_PATH", data_path("csd", "password.txt")))

    # Infraestructura
    log_path: Path = field(default_factory=lambda: _resolve_env_path("LOG_PATH", runtime_log_path("app.log")))
    db_path: Path = field(default_factory=lambda: _resolve_env_path("DB_PATH", data_path("db", "conta_sat.sqlite")))

    # Parámetros de solicitudes SAT
    rfc: str = field(default_factory=lambda: os.getenv("SAT_RFC", "").strip())
    tipo_solicitud: str = field(default_factory=lambda: os.getenv("SAT_TIPO_SOLICITUD", "CFDI").strip())  # CFDI | RETENCIONES
    modo: str = field(default_factory=lambda: os.getenv("SAT_MODO", "RECIBIDAS").strip())  # RECIBIDAS | EMITIDAS
    fecha_ini: str = field(default_factory=lambda: os.getenv("SAT_FECHA_INI", "").strip())  # YYYY-MM-DD
    fecha_fin: str = field(default_factory=lambda: os.getenv("SAT_FECHA_FIN", "").strip())  # YYYY-MM-DD

    @property
    def boveda_dir(self) -> Path:
        return _resolve_env_path("BOVEDA_DIR", data_path("boveda"))

    @property
    def organized_dir(self) -> Path:
        return data_path("organizado")

    @property
    def exports_dir(self) -> Path:
        return data_path("exports")

    @property
    def bi_exports_dir(self) -> Path:
        return data_path("bi_exports")

    @property
    def reportes_dir(self) -> Path:
        return data_path("reportes_app")

    @property
    def app_logs_dir(self) -> Path:
        return data_path("app_logs")

    @property
    def clientes_path(self) -> Path:
        return config_path("data", "config", "clientes.json")

    @property
    def clientes_example_path(self) -> Path:
        return asset_path("data", "config", "clientes.example.json")

    @property
    def rfc_names_path(self) -> Path:
        return config_path("data", "config", "rfc_names.json")

    @property
    def rfc_names_example_path(self) -> Path:
        return asset_path("data", "config", "rfc_names.example.json")

    @property
    def alertas_config_path(self) -> Path:
        return config_path("alertas", "config", "config.yaml")

    @property
    def env_path(self) -> Path:
        return preferred_env_path()


settings = Settings()
