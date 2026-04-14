from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from runtime_paths import get_runtime_setting, runtime_settings_path, save_runtime_settings
from src.utils.config import settings


OWNER_FIELD_CANDIDATES = (
    "dueno_cuenta",
    "dueño_cuenta",
    "account_owner",
    "owner",
    "responsable",
    "encargado",
    "contadora",
)

FILTER_ALL = "__all__"
FILTER_UNASSIGNED = "__unassigned__"


def normalize_owner_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def get_company_account_owner(company: dict[str, Any]) -> str | None:
    for key in OWNER_FIELD_CANDIDATES:
        owner = normalize_owner_name(company.get(key))
        if owner:
            return owner

    raw = company.get("raw")
    if isinstance(raw, dict):
        for key in OWNER_FIELD_CANDIDATES:
            owner = normalize_owner_name(raw.get(key))
            if owner:
                return owner

    return None


def list_account_owners(companies: list[dict[str, Any]]) -> list[str]:
    owners: dict[str, str] = {}
    for company in companies:
        owner = get_company_account_owner(company)
        if owner:
            owners.setdefault(owner.casefold(), owner)
    return sorted(owners.values(), key=str.casefold)


def get_owner_filter_options(companies: list[dict[str, Any]]) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [(FILTER_ALL, "Director / Todos")]
    options.extend((owner, owner) for owner in list_account_owners(companies))
    if any(get_company_account_owner(company) is None for company in companies):
        options.append((FILTER_UNASSIGNED, "Sin asignar"))
    return options


def sanitize_owner_filter(value: str | None, companies: list[dict[str, Any]]) -> str:
    if not value:
        return FILTER_ALL

    for token, _label in get_owner_filter_options(companies):
        if token == value:
            return token
        if token not in {FILTER_ALL, FILTER_UNASSIGNED} and token.casefold() == str(value).casefold():
            return token
    return FILTER_ALL


def get_owner_filter_label(value: str | None, companies: list[dict[str, Any]]) -> str:
    selected = sanitize_owner_filter(value, companies)
    for token, label in get_owner_filter_options(companies):
        if token == selected:
            return label
    return "Director / Todos"


def get_saved_owner_filter(companies: list[dict[str, Any]]) -> str:
    return sanitize_owner_filter(get_runtime_setting("ACCOUNT_OWNER_FILTER"), companies)


def save_owner_filter_preference(value: str | None) -> Path:
    selected = FILTER_ALL if not value else value
    payload = None if selected == FILTER_ALL else selected
    return save_runtime_settings({"ACCOUNT_OWNER_FILTER": payload})


def filter_companies_by_owner(companies: list[dict[str, Any]], owner_filter: str | None) -> list[dict[str, Any]]:
    selected = sanitize_owner_filter(owner_filter, companies)
    if selected == FILTER_ALL:
        return list(companies)
    if selected == FILTER_UNASSIGNED:
        return [company for company in companies if get_company_account_owner(company) is None]

    expected = selected.casefold()
    return [
        company
        for company in companies
        if (get_company_account_owner(company) or "").casefold() == expected
    ]


def normalize_boveda_root(raw_path: str | Path) -> Path:
    text = str(raw_path).strip()
    if not text:
        raise ValueError("Captura la ruta base de la carpeta compartida.")

    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        raise ValueError("La ruta de la boveda debe ser absoluta o de red compartida.")

    if candidate.name.lower() in {"zip", "extract"}:
        candidate = candidate.parent
    return candidate.resolve()


def save_boveda_root_preference(raw_path: str | Path) -> Path:
    base_dir = normalize_boveda_root(raw_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "zip").mkdir(parents=True, exist_ok=True)
    (base_dir / "extract").mkdir(parents=True, exist_ok=True)

    os.environ["BOVEDA_DIR"] = str(base_dir)
    save_runtime_settings({"BOVEDA_DIR": str(base_dir)})
    return base_dir


def clear_boveda_root_preference() -> Path:
    os.environ.pop("BOVEDA_DIR", None)
    save_runtime_settings({"BOVEDA_DIR": None})
    return settings.boveda_dir


def pilot_settings_file() -> Path:
    return runtime_settings_path()


def save_account_owner_assignments(
    assignments: dict[str, str | None],
    clientes_path: Path | None = None,
) -> tuple[int, Path]:
    path = clientes_path or settings.clientes_path
    if not path.exists():
        raise FileNotFoundError(f"No existe el catalogo de clientes en: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized_assignments = {
        str(rfc).strip().upper(): normalize_owner_name(owner)
        for rfc, owner in assignments.items()
        if str(rfc).strip()
    }

    changes = 0
    if isinstance(payload, dict):
        for rfc_key, company in payload.items():
            if not isinstance(company, dict):
                continue
            changes += _apply_owner_assignment(company, normalized_assignments.get(str(rfc_key).strip().upper()))
    elif isinstance(payload, list):
        for company in payload:
            if not isinstance(company, dict):
                continue
            rfc = str(company.get("rfc") or "").strip().upper()
            if not rfc:
                continue
            changes += _apply_owner_assignment(company, normalized_assignments.get(rfc))
    else:
        raise ValueError("clientes.json debe ser una lista o un diccionario.")

    if changes:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + os.linesep, encoding="utf-8")
    return changes, path


def _apply_owner_assignment(company: dict[str, Any], owner: str | None) -> int:
    changed = 0
    if owner:
        if company.get("dueno_cuenta") != owner:
            company["dueno_cuenta"] = owner
            changed = 1
    else:
        if "dueno_cuenta" in company:
            company.pop("dueno_cuenta", None)
            changed = 1

    for key in OWNER_FIELD_CANDIDATES:
        if key == "dueno_cuenta":
            continue
        if key in company:
            company.pop(key, None)
            changed = 1
    return changed
