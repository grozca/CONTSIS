from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:
    raise RuntimeError(
        "Falta la dependencia 'PyYAML'. Instala las dependencias de alertas antes de ejecutar el motor."
    ) from exc

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True, slots=True)
class AppPaths:
    base_dir: Path
    config_path: Path
    log_dir: Path
    data_dir: Path
    historial_db: Path
    clientes_json: Path
    exports_dir: Path


BASE_DIR = Path(__file__).resolve().parent.parent
PATHS = AppPaths(
    base_dir=BASE_DIR,
    config_path=BASE_DIR / "config" / "config.yaml",
    log_dir=BASE_DIR / "logs",
    data_dir=BASE_DIR / "data",
    historial_db=BASE_DIR / "data" / "historial_alertas.db",
    clientes_json=Path("data/config/clientes.json"),
    exports_dir=Path("data/exports"),
)

PATHS.log_dir.mkdir(exist_ok=True)
PATHS.data_dir.mkdir(exist_ok=True)

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
    with PATHS.config_path.open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def cargar_clientes() -> dict[str, Any]:
    if not PATHS.clientes_json.exists():
        return {}
    with PATHS.clientes_json.open(encoding="utf-8") as file:
        return json.load(file)
