from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from src.utils.config import settings
from src.utils.logging_cfg import setup_logging
from src.utils.sqlite_safe import connect_sqlite

log = logging.getLogger(__name__)

RFC_CONFIG_PATH = settings.clientes_path


def _parse_min(xml_bytes: bytes) -> dict[str, str]:
    """
    Extrae emisor_rfc, receptor_rfc, fecha YYYY-MM-DD y uuid.
    Soporta CFDI 3.3/4.0.
    """
    out = {"emisor_rfc": "", "receptor_rfc": "", "fecha": "", "uuid": ""}
    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(xml_bytes, parser=parser)

        fecha = root.get("Fecha") or root.get("fecha") or ""
        out["fecha"] = fecha[:10] if len(fecha) >= 10 else ""

        em_nodes = root.xpath("//*[local-name()='Emisor']")
        rc_nodes = root.xpath("//*[local-name()='Receptor']")
        em = em_nodes[0] if em_nodes else None
        rc = rc_nodes[0] if rc_nodes else None

        out["emisor_rfc"] = ((em.get("Rfc") or em.get("rfc") or "") if em is not None else "").upper()
        out["receptor_rfc"] = ((rc.get("Rfc") or rc.get("rfc") or "") if rc is not None else "").upper()

        tfd_nodes = root.xpath("//*[local-name()='TimbreFiscalDigital']")
        if tfd_nodes:
            out["uuid"] = (tfd_nodes[0].get("UUID") or "").upper()
    except Exception as exc:
        log.warning("XML malformado (%s bytes): %s", len(xml_bytes), exc)
    return out


def _yyyy_mm(info: dict[str, str]) -> tuple[str, str]:
    fecha = info.get("fecha") or ""
    if len(fecha) >= 7:
        return fecha[0:4], fecha[5:7]
    return "0000", "00"


def _safe_filename(info: dict[str, str], xml_bytes: bytes) -> str:
    base = info.get("uuid") or hashlib.sha1(xml_bytes).hexdigest().upper()
    return f"{base}.xml"


def _normalized_stem(filename: str) -> str:
    stem = Path(filename).stem.upper()
    if "_" in stem:
        base, suffix = stem.rsplit("_", 1)
        if suffix.isdigit():
            return base
    return stem


def _load_existing_stems(dest_dir: Path, cache: dict[Path, set[str]]) -> set[str]:
    known = cache.get(dest_dir)
    if known is None:
        known = {
            _normalized_stem(path.name)
            for path in dest_dir.glob("*.xml")
            if path.is_file()
        }
        cache[dest_dir] = known
    return known


def _load_own_rfcs() -> set[str]:
    try:
        if RFC_CONFIG_PATH.is_file():
            data = json.loads(RFC_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(key).strip().upper() for key in data.keys() if str(key).strip()}
    except Exception as exc:
        log.warning("No se pudo leer %s: %s", RFC_CONFIG_PATH, exc)
    return set()


def _ensure_base_dirs_for_rfcs(root: Path, rfcs: set[str]) -> None:
    for rfc in rfcs:
        (root / rfc / "EMITIDAS").mkdir(parents=True, exist_ok=True)
        (root / rfc / "RECIBIDAS").mkdir(parents=True, exist_ok=True)


def _ensure_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS paquetes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          id_solicitud TEXT,
          id_paquete TEXT UNIQUE,
          estado TEXT,
          path_zip TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _discover_unregistered_zips(con: sqlite3.Connection, zip_dir: Path) -> int:
    changes_before = con.total_changes
    for zip_path in zip_dir.glob("*.zip"):
        _register_zip(con, zip_path)
    return con.total_changes - changes_before


def _register_zip(con: sqlite3.Connection, zip_path: Path) -> int:
    id_paquete = zip_path.stem
    con.execute(
        "INSERT OR IGNORE INTO paquetes(id_solicitud,id_paquete,estado,path_zip) VALUES (?,?,?,?)",
        ("MANUAL", id_paquete, "DESCARGADO", str(zip_path)),
    )
    row = con.execute(
        "SELECT id, COALESCE(estado, '') FROM paquetes WHERE id_paquete = ?",
        (id_paquete,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"No se pudo registrar el ZIP {zip_path}")

    packet_id = int(row[0])
    current_status = str(row[1] or "")
    if current_status != "EXTRAIDO":
        con.execute(
            "UPDATE paquetes SET path_zip = ?, estado = 'DESCARGADO' WHERE id = ?",
            (str(zip_path), packet_id),
        )
    return packet_id


def _mark_zip_status(con: sqlite3.Connection, packet_id: int, status: str) -> None:
    con.execute("UPDATE paquetes SET estado = ? WHERE id = ?", (status, packet_id))


def _resolve_destination(
    extract_root: Path,
    info: dict[str, str],
    own_rfcs: set[str],
) -> tuple[Path, str, str] | None:
    emisor = (info.get("emisor_rfc") or "").upper()
    receptor = (info.get("receptor_rfc") or "").upper()
    year, month = _yyyy_mm(info)

    if year == "0000" or month == "00":
        return None

    if emisor in own_rfcs:
        return extract_root / emisor / "EMITIDAS" / year / month, emisor, "EMITIDAS"
    if receptor in own_rfcs:
        return extract_root / receptor / "RECIBIDAS" / year / month, receptor, "RECIBIDAS"
    return None


def _new_summary(zip_path: Path | None = None) -> dict[str, Any]:
    return {
        "zip_name": zip_path.name if zip_path else None,
        "zip_path": str(zip_path) if zip_path else None,
        "zip_files": 1 if zip_path else 0,
        "xml_en_zip": 0,
        "extraidos": 0,
        "duplicados": 0,
        "omitidos_terceros": 0,
        "errores": 0,
        "rfcs_detectados": set(),
        "roles_detectados": set(),
        "periodos_detectados": set(),
        "targets_detectados": set(),
        "fecha_min": None,
        "fecha_max": None,
    }


def _merge_summaries(target: dict[str, Any], current: dict[str, Any]) -> None:
    target["zip_files"] += current.get("zip_files", 0)
    target["xml_en_zip"] += current.get("xml_en_zip", 0)
    target["extraidos"] += current.get("extraidos", 0)
    target["duplicados"] += current.get("duplicados", 0)
    target["omitidos_terceros"] += current.get("omitidos_terceros", 0)
    target["errores"] += current.get("errores", 0)
    target["rfcs_detectados"].update(current.get("rfcs_detectados", set()))
    target["roles_detectados"].update(current.get("roles_detectados", set()))
    target["periodos_detectados"].update(current.get("periodos_detectados", set()))
    target["targets_detectados"].update(current.get("targets_detectados", set()))

    fecha_min = current.get("fecha_min")
    fecha_max = current.get("fecha_max")
    if fecha_min and (not target["fecha_min"] or fecha_min < target["fecha_min"]):
        target["fecha_min"] = fecha_min
    if fecha_max and (not target["fecha_max"] or fecha_max > target["fecha_max"]):
        target["fecha_max"] = fecha_max


def _finalize_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        **summary,
        "rfcs_detectados": sorted(summary.get("rfcs_detectados", set())),
        "roles_detectados": sorted(summary.get("roles_detectados", set())),
        "periodos_detectados": sorted(summary.get("periodos_detectados", set())),
        "targets_detectados": [
            {"rfc": rfc, "periodo": periodo}
            for rfc, periodo in sorted(summary.get("targets_detectados", set()))
        ],
    }


def _log_summary(summary: dict[str, Any]) -> None:
    rfcs = ", ".join(summary["rfcs_detectados"]) if summary["rfcs_detectados"] else "N/A"
    periodos = ", ".join(summary["periodos_detectados"]) if summary["periodos_detectados"] else "N/A"
    rango = summary["fecha_min"] or "N/A"
    if summary.get("fecha_max") and summary["fecha_max"] != summary["fecha_min"]:
        rango = f"{summary['fecha_min']} a {summary['fecha_max']}"

    log.info(
        "[OK] %s -> xml=%d, extraidos=%d, duplicados=%d, omitidos_terceros=%d, errores=%d, rfcs=%s, periodos=%s, fechas=%s",
        summary.get("zip_name") or "lote",
        summary["xml_en_zip"],
        summary["extraidos"],
        summary["duplicados"],
        summary["omitidos_terceros"],
        summary["errores"],
        rfcs,
        periodos,
        rango,
    )
    print(
        f"[OK] {summary.get('zip_name') or 'lote'} -> xml={summary['xml_en_zip']}, "
        f"extraidos={summary['extraidos']}, duplicados={summary['duplicados']}, "
        f"omitidos_terceros={summary['omitidos_terceros']}, errores={summary['errores']}, "
        f"rfcs={rfcs}, periodos={periodos}, fechas={rango}"
    )


def _process_zip_file(
    zip_path: Path,
    extract_root: Path,
    own_rfcs: set[str],
    existing_stems_cache: dict[Path, set[str]],
) -> dict[str, Any]:
    summary = _new_summary(zip_path)

    if not zip_path.exists():
        raise FileNotFoundError(f"No existe el ZIP: {zip_path}")

    with zipfile.ZipFile(zip_path, "r") as zip_file:
        for member in zip_file.infolist():
            member_name = member.filename
            if member.is_dir() or not member_name.lower().endswith(".xml"):
                continue

            summary["xml_en_zip"] += 1

            try:
                xml_bytes = zip_file.read(member_name)
                info = _parse_min(xml_bytes)
                destination = _resolve_destination(extract_root, info, own_rfcs)
                if destination is None:
                    summary["omitidos_terceros"] += 1
                    continue

                dest_dir, rfc_destino, rol = destination
                summary["rfcs_detectados"].add(rfc_destino)
                summary["roles_detectados"].add(rol)

                year, month = _yyyy_mm(info)
                summary["periodos_detectados"].add(f"{year}-{month}")
                summary["targets_detectados"].add((rfc_destino, f"{year}-{month}"))

                fecha = info.get("fecha") or ""
                if fecha and (not summary["fecha_min"] or fecha < summary["fecha_min"]):
                    summary["fecha_min"] = fecha
                if fecha and (not summary["fecha_max"] or fecha > summary["fecha_max"]):
                    summary["fecha_max"] = fecha

                dest_dir.mkdir(parents=True, exist_ok=True)

                filename = _safe_filename(info, xml_bytes)
                normalized_stem = _normalized_stem(filename)
                known_stems = _load_existing_stems(dest_dir, existing_stems_cache)

                if normalized_stem in known_stems or (dest_dir / filename).exists():
                    summary["duplicados"] += 1
                    continue

                (dest_dir / filename).write_bytes(xml_bytes)
                known_stems.add(normalized_stem)
                summary["extraidos"] += 1
            except Exception as exc:
                summary["errores"] += 1
                log.error("Error extrayendo %s de %s: %s", member_name, zip_path.name, exc)

    return _finalize_summary(summary)


def run(zip_path: str | Path | None = None) -> dict[str, Any]:
    setup_logging(settings.log_path)
    log.info("R6: Descomprimir y organizar por RFC/EMITIDAS-RECIBIDAS/ANIO/MES")

    base_boveda = Path(settings.boveda_dir)
    zip_dir = base_boveda / "zip"
    extract_root = base_boveda / "extract"
    zip_dir.mkdir(parents=True, exist_ok=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    own_rfcs = _load_own_rfcs()
    if own_rfcs:
        _ensure_base_dirs_for_rfcs(extract_root, own_rfcs)
    else:
        log.warning("No hay RFCs propios en %s. No se extraeran XML de terceros.", RFC_CONFIG_PATH)

    con = connect_sqlite(settings.db_path)
    _ensure_tables(con)
    existing_stems_cache: dict[Path, set[str]] = {}

    try:
        if zip_path is not None:
            target_zip = Path(zip_path)
            packet_id = _register_zip(con, target_zip)
            con.commit()

            try:
                summary = _process_zip_file(target_zip, extract_root, own_rfcs, existing_stems_cache)
                _mark_zip_status(con, packet_id, "EXTRAIDO")
                con.commit()
            except zipfile.BadZipFile:
                _mark_zip_status(con, packet_id, "ERROR")
                con.commit()
                raise

            _log_summary(summary)
            return summary

        _discover_unregistered_zips(con, zip_dir)
        con.commit()

        rows = list(
            con.execute(
                "SELECT id, path_zip FROM paquetes WHERE path_zip IS NOT NULL AND COALESCE(estado, '') != 'EXTRAIDO'"
            )
        )
        if not rows:
            summary = _finalize_summary(_new_summary())
            log.info("R6: No hay paquetes pendientes para descomprimir")
            print("No hay paquetes pendientes para descomprimir.")
            return summary

        total_summary = _new_summary()
        for packet_id, raw_path in rows:
            current_zip = Path(raw_path)
            if not current_zip.exists():
                log.warning("ZIP no existe: %s", current_zip)
                _mark_zip_status(con, packet_id, "ERROR")
                con.commit()
                continue

            try:
                summary = _process_zip_file(current_zip, extract_root, own_rfcs, existing_stems_cache)
                _mark_zip_status(con, packet_id, "EXTRAIDO")
            except zipfile.BadZipFile as exc:
                log.error("ZIP corrupto %s: %s", current_zip, exc)
                _mark_zip_status(con, packet_id, "ERROR")
                summary = _finalize_summary(_new_summary(current_zip))
                summary["errores"] = 1
            con.commit()
            _merge_summaries(total_summary, summary)
            _log_summary(summary)

        final_summary = _finalize_summary(total_summary)
        log.info(
            "R6: Finalizado. zip_files=%d, xml=%d, extraidos=%d, duplicados=%d, omitidos_terceros=%d, errores=%d",
            final_summary["zip_files"],
            final_summary["xml_en_zip"],
            final_summary["extraidos"],
            final_summary["duplicados"],
            final_summary["omitidos_terceros"],
            final_summary["errores"],
        )
        print(
            f"R6: Finalizado. zip_files={final_summary['zip_files']}, xml={final_summary['xml_en_zip']}, "
            f"extraidos={final_summary['extraidos']}, duplicados={final_summary['duplicados']}, "
            f"omitidos_terceros={final_summary['omitidos_terceros']}, errores={final_summary['errores']}"
        )
        return final_summary
    finally:
        con.close()
