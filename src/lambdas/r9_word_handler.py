# src/lambdas/r9_word_handler.py
from __future__ import annotations
import os, json, boto3
from pathlib import Path
from src.core.r9_word_core import build_month_summary_docx

s3 = boto3.client("s3")
BUCKET_EXPORTS = os.environ.get("BUCKET_EXPORTS","")

def _ensure_local_exports(rfc: str, yyyy_mm: str) -> Path:
    base = Path(f"/tmp/{rfc}/{yyyy_mm}")
    base.mkdir(parents=True, exist_ok=True)
    # Descargar ambos Excels si existen
    for role in ("RECIBIDAS","EMITIDAS"):
        key = f"{rfc}/{yyyy_mm}/{rfc}_{yyyy_mm}_{role}_Facturas.xlsx"
        try:
            s3.download_file(BUCKET_EXPORTS, key, str(base / f"{rfc}_{yyyy_mm}_{role}_Facturas.xlsx"))
        except s3.exceptions.NoSuchKey:
            pass
        except Exception:
            pass
    return Path("/tmp")

def handler(event, context):
    """
    event = {
      "rfc": "IIS891106AE6",
      "yyyy_mm": "2025-07"
    }
    Lee: s3://exports/<RFC>/<YYYY-MM>/<RFC>_<YYYY-MM>_<ROL>_Facturas.xlsx
    Escribe: s3://exports/<RFC>/<YYYY-MM>/RESUMEN_<RFC>_<YYYY-MM>.docx (+ manifest.json)
    """
    rfc = event["rfc"].upper()
    yyyy_mm = event["yyyy_mm"]

    exports_dir = _ensure_local_exports(rfc, yyyy_mm)  # crea /tmp/... y baja Excels
    out_doc = build_month_summary_docx(exports_dir, rfc, yyyy_mm)

    # Subir docx y manifest
    out_key = f"{rfc}/{yyyy_mm}/{out_doc.name}"
    s3.upload_file(str(out_doc), BUCKET_EXPORTS, out_key)

    man_local = exports_dir / rfc / yyyy_mm / "manifest.json"
    man_key = f"{rfc}/{yyyy_mm}/manifest.json"
    if man_local.exists():
        s3.upload_file(str(man_local), BUCKET_EXPORTS, man_key)

    return {"status": "ok", "docx": f"s3://{BUCKET_EXPORTS}/{out_key}", "manifest": f"s3://{BUCKET_EXPORTS}/{man_key}"}
