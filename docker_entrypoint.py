from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
RUNTIME_ROOT = Path(os.getenv("CONTSIS_HOME", "/app/runtime")).expanduser()


def _seed_if_missing(source: Path, target: Path) -> None:
    if not source.exists() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def ensure_runtime_seed() -> None:
    mappings = [
        (
            APP_ROOT / "data" / "config" / "clientes.example.json",
            RUNTIME_ROOT / "data" / "config" / "clientes.json",
        ),
        (
            APP_ROOT / "data" / "config" / "rfc_names.example.json",
            RUNTIME_ROOT / "data" / "config" / "rfc_names.json",
        ),
        (
            APP_ROOT / "alertas" / "config" / "config.example.yaml",
            RUNTIME_ROOT / "alertas" / "config" / "config.yaml",
        ),
    ]
    for source, target in mappings:
        _seed_if_missing(source, target)


def main() -> None:
    ensure_runtime_seed()
    host = os.getenv("CONTSIS_SERVER_HOST", "0.0.0.0").strip() or "0.0.0.0"
    port = os.getenv("CONTSIS_SERVER_PORT", "8501").strip() or "8501"
    os.execvp(
        "streamlit",
        [
            "streamlit",
            "run",
            "app.py",
            f"--server.port={port}",
            f"--server.address={host}",
        ],
    )


if __name__ == "__main__":
    main()
