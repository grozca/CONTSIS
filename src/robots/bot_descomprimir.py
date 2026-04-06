# src/robots/r6_descomprimir.py
import logging
import sqlite3
import zipfile
import hashlib
import json
from io import BytesIO
from pathlib import Path

from lxml import etree  # pip install lxml

from src.utils.config import settings
from src.utils.logging_cfg import setup_logging

log = logging.getLogger(__name__)

RFC_CONFIG_PATH = Path("data/config/clientes.json") 

# ---------------- XML helpers ----------------

def _parse_min(xml_bytes: bytes):
    """
    Extrae: emisor_rfc, receptor_rfc, fecha YYYY-MM-DD, uuid (si hay timbre).
    Soporta CFDI 3.3 y 4.0. Usa XPath real (no ElementPath).
    """
    out = {"emisor_rfc": "", "receptor_rfc": "", "fecha": "", "uuid": ""}
    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(xml_bytes, parser=parser)

        # Fecha del comprobante (atributo Fecha / fecha)
        fecha = root.get("Fecha") or root.get("fecha") or ""
        out["fecha"] = fecha[:10] if len(fecha) >= 10 else ""

        # Emisor / Receptor por XPath con local-name()
        em_nodes = root.xpath("//*[local-name()='Emisor']")
        rc_nodes = root.xpath("//*[local-name()='Receptor']")
        em = em_nodes[0] if em_nodes else None
        rc = rc_nodes[0] if rc_nodes else None

        out["emisor_rfc"] = ((em.get("Rfc") or em.get("rfc") or "") if em is not None else "").upper()
        out["receptor_rfc"] = ((rc.get("Rfc") or rc.get("rfc") or "") if rc is not None else "").upper()

        # Timbre fiscal
        tfd_nodes = root.xpath("//*[local-name()='TimbreFiscalDigital']")
        if tfd_nodes:
            out["uuid"] = (tfd_nodes[0].get("UUID") or "").upper()

    except Exception as e:
        log.warning("XML malformado (%s bytes): %s", len(xml_bytes), e)
    return out

def _yyyy_mm(info):
    f = info.get("fecha") or ""
    if len(f) >= 7:
        return f[0:4], f[5:7]
    return "0000", "00"

def _safe_filename(info, xml_bytes: bytes) -> str:
    base = info.get("uuid") or hashlib.sha1(xml_bytes).hexdigest().upper()
    return f"{base}.xml"

def _unique_path(dest_dir: Path, filename: str) -> Path:
    p = dest_dir / filename
    if not p.exists():
        return p
    stem, suf = p.stem, 2
    while True:
        cand = dest_dir / f"{stem}_{suf}{p.suffix}"
        if not cand.exists():
            return cand
        suf += 1

# ---------------- RFC propios ----------------

def _load_own_rfcs() -> set:
    """
    Lee las claves del JSON (RFCs propios). Si no existe, regresa set vacío.
    """
    try:
        if RFC_CONFIG_PATH.is_file():
            data = json.loads(RFC_CONFIG_PATH.read_text(encoding="utf-8"))
            return {k.strip().upper() for k in data.keys()}
    except Exception as e:
        log.warning("No se pudo leer %s: %s", RFC_CONFIG_PATH, e)
    return set()

def _ensure_base_dirs_for_rfcs(root: Path, rfcs: set):
    for rfc in rfcs:
        (root / rfc / "EMITIDAS").mkdir(parents=True, exist_ok=True)
        (root / rfc / "RECIBIDAS").mkdir(parents=True, exist_ok=True)

# ---------------- DB helpers ----------------

def _ensure_tables(con: sqlite3.Connection):
    con.execute("""
    CREATE TABLE IF NOT EXISTS paquetes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      id_solicitud TEXT,
      id_paquete TEXT UNIQUE,
      estado TEXT,
      path_zip TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

def _discover_unregistered_zips(con: sqlite3.Connection, zip_dir: Path) -> int:
    n = 0
    for z in zip_dir.glob("*.zip"):
        con.execute(
            "INSERT OR IGNORE INTO paquetes(id_solicitud,id_paquete,estado,path_zip) VALUES (?,?,?,?)",
            ("MANUAL", z.stem, "DESCARGADO", str(z))
        )
        n += con.total_changes
    return n

# ---------------- Enrutado ----------------

def _dest_for_info(extract_root: Path, info: dict, own_rfcs: set) -> Path | None:
    """
    Si Emisor ∈ propios -> <RFC>/EMITIDAS/AAAA/MM
    elif Receptor ∈ propios -> <RFC>/RECIBIDAS/AAAA/MM
    else -> None (no extraer; no queremos crear carpetas para terceros)
    """
    em = (info.get("emisor_rfc") or "").upper()
    rc = (info.get("receptor_rfc") or "").upper()
    yyyy, mm = _yyyy_mm(info)

    if em in own_rfcs:
        return extract_root / em / "EMITIDAS" / yyyy / mm
    if rc in own_rfcs:
        return extract_root / rc / "RECIBIDAS" / yyyy / mm
    return None

# ---------------- Main ----------------

def run():
    setup_logging(settings.log_path)
    log.info("R6: Descomprimir y ORGANIZAR por RFC/EMITIDAS-RECIBIDAS/AÑO/MES (XPath real, CFDI 3.3/4.0)")

    base_boveda = Path(settings.boveda_dir)
    zip_dir = base_boveda / "zip"
    extract_root = base_boveda / "extract"
    zip_dir.mkdir(parents=True, exist_ok=True)
    extract_root.mkdir(parents=True, exist_ok=True)

    own_rfcs = _load_own_rfcs()
    if own_rfcs:
        _ensure_base_dirs_for_rfcs(extract_root, own_rfcs)
    else:
        log.warning("No hay RFCs propios en %s. No se extraerán XML de terceros.", RFC_CONFIG_PATH)

    con = sqlite3.connect(settings.db_path)
    _ensure_tables(con)

    # Registrar ZIPs manuales presentes (idempotente)
    _discover_unregistered_zips(con, zip_dir)
    con.commit()

    rows = list(con.execute("SELECT id, id_paquete, path_zip FROM paquetes WHERE path_zip IS NOT NULL"))
    if not rows:
        log.info("R6: No hay paquetes para descomprimir")
        print("No hay paquetes para descomprimir.")
        con.close()
        return

    total_xml = 0
    total_skipped = 0

    for pid, id_paquete, path_zip in rows:
        zpath = Path(path_zip)
        if not zpath.exists():
            log.warning("ZIP no existe: %s", zpath)
            continue

        extracted = 0
        skipped = 0
        with zipfile.ZipFile(zpath, "r") as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".xml"):
                    continue
                try:
                    xmlb = zf.read(name)
                    info = _parse_min(xmlb)
                    dest_dir = _dest_for_info(extract_root, info, own_rfcs)
                    if dest_dir is None:
                        skipped += 1
                        continue  # no pertenece a tus RFC: no se extrae

                    dest_dir.mkdir(parents=True, exist_ok=True)
                    filename = _safe_filename(info, xmlb)
                    dest_file = _unique_path(dest_dir, filename)
                    if not dest_file.exists():
                        dest_file.write_bytes(xmlb)
                        extracted += 1
                except Exception as e:
                    log.error("Error extrayendo %s de %s: %s", name, zpath.name, e)

        con.execute("UPDATE paquetes SET estado='EXTRAIDO' WHERE id=?", (pid,))
        con.commit()

        total_xml += extracted
        total_skipped += skipped
        log.info("[OK] %s -> extraídos=%d, omitidos_terceros=%d", zpath.name, extracted, skipped)
        print(f"[OK] {zpath.name} -> extraídos={extracted}, omitidos_terceros={skipped}")

    con.close()
    log.info("R6: Finalizado. XML extraídos=%d, omitidos_terceros=%d", total_xml, total_skipped)
    print(f"R6: Finalizado. XML extraídos={total_xml}, omitidos_terceros={total_skipped}")
