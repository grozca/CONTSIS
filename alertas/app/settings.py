from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise RuntimeError(
        "Falta la dependencia 'PyYAML' en el Python activo. "
        "Activa la virtualenv del proyecto o ejecuta: "
        ".\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt -r alertas/requirements.txt"
    ) from exc

from runtime_paths import bundle_root, config_path, data_path, load_project_env, runtime_path


load_project_env()


@dataclass(frozen=True, slots=True)
class AppPaths:
    base_dir: Path
    config_path: Path
    log_dir: Path
    data_dir: Path
    historial_db: Path
    clientes_json: Path
    exports_dir: Path


PATHS = AppPaths(
    base_dir=bundle_root(),
    config_path=config_path("alertas", "config", "config.yaml"),
    log_dir=runtime_path("logs", "alertas"),
    data_dir=runtime_path("data", "alertas"),
    historial_db=runtime_path("data", "alertas", "historial_alertas.db"),
    clientes_json=config_path("data", "config", "clientes.json"),
    exports_dir=data_path("exports"),
)

PATHS.log_dir.mkdir(parents=True, exist_ok=True)
PATHS.data_dir.mkdir(parents=True, exist_ok=True)

MESES_ES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def cargar_config() -> dict[str, Any]:
    if not PATHS.config_path.exists():
        raise FileNotFoundError(f"No existe config.yaml en: {PATHS.config_path}")
    with PATHS.config_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def cargar_clientes() -> dict[str, Any]:
    if not PATHS.clientes_json.exists():
        return {}
    with PATHS.clientes_json.open(encoding="utf-8") as file:
        return json.load(file)
