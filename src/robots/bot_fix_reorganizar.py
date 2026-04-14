# src/robots/r6_fix_reorganizar.py
import logging
import json
import hashlib
from pathlib import Path
from shutil import move

from lxml import etree  # pip install lxml

from src.utils.config import settings
from src.utils.logging_cfg import setup_logging

log = logging.getLogger(__name__)

RFC_CONFIG_PATH = settings.clientes_path

def _load_own_rfcs() -> set:
    try:
        if RFC_CONFIG_PATH.is_file():
            data = json.loads(RFC_CONFIG_PATH.read_text(encoding="utf-8"))
            return {k.strip().upper() for k in data.keys()}
    except Exception as e:
        log.warning("No se pudo leer %s: %s", RFC_CONFIG_PATH, e)
    return set()

def _parse_min(xml_bytes: bytes):
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
    except Exception as e:
        log.warning("XML malformado: %s", e)
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

def run():
    setup_logging(settings.log_path)
    log.info("R6_FIX: Reorganizar XML ya extraídos por RFC/EMITIDAS-RECIBIDAS/AÑO/MES (solo RFC propios)")

    extract_root = Path(settings.boveda_dir) / "extract"
    own_rfcs = _load_own_rfcs()
    if not own_rfcs:
        log.error("No hay RFCs propios en %s. Abortando.", RFC_CONFIG_PATH)
        print("No hay RFCs propios configurados.")
        return

    for rfc in own_rfcs:
        (extract_root / rfc / "EMITIDAS").mkdir(parents=True, exist_ok=True)
        (extract_root / rfc / "RECIBIDAS").mkdir(parents=True, exist_ok=True)

    all_xml = list(extract_root.rglob("*.xml"))
    moved, skipped = 0, 0

    for fp in all_xml:
        try:
            xmlb = fp.read_bytes()
            info = _parse_min(xmlb)
            em = (info.get("emisor_rfc") or "").upper()
            rc = (info.get("receptor_rfc") or "").upper()
            yyyy, mm = _yyyy_mm(info)

            dest = None
            if em in own_rfcs:
                dest = extract_root / em / "EMITIDAS" / yyyy / mm
            elif rc in own_rfcs:
                dest = extract_root / rc / "RECIBIDAS" / yyyy / mm

            if dest is None:
                skipped += 1
                continue

            dest.mkdir(parents=True, exist_ok=True)
            try:
                # si ya está en la ruta final, no lo muevas
                fp.relative_to(dest)
                continue
            except Exception:
                pass

            filename = _safe_filename(info, xmlb)
            final_path = _unique_path(dest, filename)
            if final_path != fp:
                move(str(fp), str(final_path))
                moved += 1

        except Exception as e:
            log.error("R6_FIX: Error con %s: %s", fp, e)

    log.info("R6_FIX: terminado. movidos=%d, omitidos_terceros_o_correctos=%d", moved, skipped)
    print(f"R6_FIX: terminado. movidos={moved}, omitidos_terceros_o_correctos={skipped}")
