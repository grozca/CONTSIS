# src/lambdas/r8_excel_handler.py
from __future__ import annotations
import os, io, json, boto3
from pathlib import Path
from typing import List
from src.core.r8_excel_core import build_monthly_excels_from_xml_bytes, save_excels_with_format

s3 = boto3.client("s3")

BUCKET_BOVEDA  = os.environ.get("BUCKET_BOVEDA",  "")
BUCKET_EXPORTS = os.environ.get("BUCKET_EXPORTS", "")

def _list_xml_keys(bucket: str, prefix: str) -> List[str]:
    keys = []
    token = None
    while True:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, ContinuationToken=token) if token else \
               s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        for it in resp.get("Contents", []):
            if it["Key"].lower().endswith(".xml"):
                keys.append(it["Key"])
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return sorted(keys)

def handler(event, context):
    """
    event = {
      "rfc": "IIS891106AE6",
      "yyyy_mm": "2025-07",
      "roles": ["RECIBIDAS","EMITIDAS"]   # opcional (default ambos)
    }
    Estructura esperada en boveda:
      A) s3://<boveda>/extract/<RFC>/<YYYY>/<MM>/<ROL>/*.xml
      B) s3://<boveda>/extract/<RFC>/<ROL>/<YYYY>/<MM>/*.xml
    Salida en exports:
      s3://<exports>/<RFC>/<YYYY-MM>/<RFC>_<YYYY-MM>_<ROL>_Facturas.xlsx
    """
    rfc = event["rfc"].upper()
    yyyy_mm = event["yyyy_mm"]
    year, month = yyyy_mm.split("-")
    roles = [r.upper() for r in event.get("roles", ["RECIBIDAS","EMITIDAS"])]

    results = []
    for role in roles:
        # dos posibles prefijos
        p1 = f"extract/{rfc}/{year}/{month}/{role}/"
        p2 = f"extract/{rfc}/{role}/{year}/{month}/"

        keys = _list_xml_keys(BUCKET_BOVEDA, p1)
        if not keys:
            keys = _list_xml_keys(BUCKET_BOVEDA, p2)

        blobs: List[bytes] = []
        for k in keys:
            obj = s3.get_object(Bucket=BUCKET_BOVEDA, Key=k)
            blobs.append(obj["Body"].read())

        sheets = build_monthly_excels_from_xml_bytes(blobs)

        # Guardar en /tmp y subir
        out_dir = Path(f"/tmp/{rfc}/{yyyy_mm}")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{rfc}_{yyyy_mm}_{role}_Facturas.xlsx"
        save_excels_with_format(sheets, out_path)

        export_key = f"{rfc}/{yyyy_mm}/{out_path.name}"
        s3.upload_file(str(out_path), BUCKET_EXPORTS, export_key)
        results.append(f"s3://{BUCKET_EXPORTS}/{export_key}")

    return {"status": "ok", "files": results}
