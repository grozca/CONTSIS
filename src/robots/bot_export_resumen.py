# src/robots/r9_export_resumen.py
# R9 — Genera Word mensual RESUMEN_<RFC>_<YYYY-MM>.docx
# Lee los Excels creados por R8 en:
# data/exports/<RFC>/<YYYY-MM>/<RFC>_<YYYY-MM>_<ROL>_Facturas.xlsx

from __future__ import annotations
import argparse, json
from pathlib import Path
from src.core.r9_word_core import build_month_summary_docx
from src.utils.config import settings

EXPORTS_DIR = Path(settings.exports_dir)


def main():
    ap = argparse.ArgumentParser(description="R9 - Genera Word Resumen mensual por RFC.")
    ap.add_argument("--rfc", required=True, help="RFC a procesar")
    ap.add_argument("--yyyy_mm", required=True, help="Periodo en formato YYYY-MM")
    a = ap.parse_args()

    out = build_month_summary_docx(EXPORTS_DIR, a.rfc.upper(), a.yyyy_mm)
    print(json.dumps({"status": "ok", "file": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
