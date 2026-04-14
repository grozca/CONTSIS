from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path

try:
    from dotenv import dotenv_values, load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is already part of the project requirements.
    dotenv_values = None
    load_dotenv = None


APP_NAME = "CONTSIS"


@lru_cache(maxsize=1)
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


@lru_cache(maxsize=1)
def bundle_root() -> Path:
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass).resolve()
        return executable_root()
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def executable_root() -> Path:
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _pre_runtime_env_candidates() -> list[Path]:
    roots = [bundle_root(), executable_root()]
    candidates: list[Path] = []
    for root in roots:
        candidates.append(root / "alertas" / ".env")
        candidates.append(root / ".env")
    return candidates


@lru_cache(maxsize=1)
def _load_pre_runtime_env() -> None:
    if load_dotenv is None:
        return
    for candidate in _pre_runtime_env_candidates():
        if candidate.exists():
            load_dotenv(candidate, override=True)


@lru_cache(maxsize=1)
def runtime_root() -> Path:
    _load_pre_runtime_env()
    configured = os.getenv("CONTSIS_HOME", "").strip()
    if configured:
        root = Path(configured).expanduser()
    elif not is_frozen():
        root = bundle_root()
    else:
        local_appdata = os.getenv("LOCALAPPDATA", "").strip()
        if local_appdata:
            root = Path(local_appdata) / APP_NAME
        else:
            root = Path.home() / f".{APP_NAME.lower()}"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _all_env_candidates() -> list[Path]:
    roots = [bundle_root(), executable_root(), runtime_root()]
    candidates: list[Path] = []
    for root in roots:
        candidates.append(root / "alertas" / ".env")
        candidates.append(root / ".env")
    return candidates


@lru_cache(maxsize=1)
def load_project_env() -> None:
    _load_pre_runtime_env()
    if load_dotenv is None:
        return
    for candidate in _all_env_candidates():
        if candidate.exists():
            load_dotenv(candidate, override=True)


def merged_dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if dotenv_values is None:
        return values
    for candidate in _all_env_candidates():
        if not candidate.exists():
            continue
        for key, value in dotenv_values(candidate).items():
            if value is not None:
                values[str(key)] = str(value)
    return values


def preferred_env_path() -> Path:
    preferred = [
        runtime_root() / ".env",
        executable_root() / ".env",
        bundle_root() / ".env",
        runtime_root() / "alertas" / ".env",
        executable_root() / "alertas" / ".env",
        bundle_root() / "alertas" / ".env",
    ]
    for candidate in preferred:
        if candidate.exists():
            return candidate
    return runtime_root() / ".env"


def runtime_settings_path() -> Path:
    path = runtime_path("config", "pilot_settings.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def load_runtime_settings() -> dict[str, str]:
    path = runtime_settings_path()
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}

    if not isinstance(payload, dict):
        return {}

    values: dict[str, str] = {}
    for key, value in payload.items():
        normalized_key = str(key).strip()
        if not normalized_key or value is None:
            continue
        values[normalized_key] = str(value).strip()
    return values


def get_runtime_setting(name: str) -> str:
    return load_runtime_settings().get(str(name).strip(), "").strip()


def save_runtime_settings(updates: dict[str, object | None]) -> Path:
    current = dict(load_runtime_settings())
    for key, value in updates.items():
        normalized_key = str(key).strip()
        if not normalized_key:
            continue

        normalized_value = "" if value is None else str(value).strip()
        if not normalized_value:
            current.pop(normalized_key, None)
        else:
            current[normalized_key] = normalized_value

    path = runtime_settings_path()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + os.linesep, encoding="utf-8")
    load_runtime_settings.cache_clear()
    return path


def _resolve_existing(roots: list[Path], *parts: str) -> Path:
    relative_parts = tuple(str(part) for part in parts)
    for root in roots:
        candidate = root.joinpath(*relative_parts)
        if candidate.exists():
            return candidate
    return roots[0].joinpath(*relative_parts)


def asset_path(*parts: str) -> Path:
    return _resolve_existing([executable_root(), bundle_root()], *parts)


def config_path(*parts: str) -> Path:
    return _resolve_existing([runtime_root(), executable_root(), bundle_root()], *parts)


def runtime_path(*parts: str) -> Path:
    relative_parts = tuple(str(part) for part in parts)
    return runtime_root().joinpath(*relative_parts)


def data_path(*parts: str) -> Path:
    return runtime_path("data", *parts)


def log_path(*parts: str) -> Path:
    return runtime_path("logs", *parts)
