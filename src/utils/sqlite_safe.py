from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 60.0


def _sqlite_timeout_seconds() -> float:
    raw_value = os.getenv("SQLITE_BUSY_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_TIMEOUT_SECONDS

    try:
        timeout = float(raw_value)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return max(timeout, 1.0)


def connect_sqlite(db_path: str | Path, *, timeout_seconds: float | None = None) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    timeout = timeout_seconds if timeout_seconds is not None else _sqlite_timeout_seconds()
    timeout = max(float(timeout), 1.0)
    busy_timeout_ms = int(timeout * 1000)

    conn = sqlite3.connect(path, timeout=timeout)

    # Prefer conservative settings for shared folders during the pilot.
    conn.execute(f"PRAGMA busy_timeout = {busy_timeout_ms};")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = DELETE;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn
