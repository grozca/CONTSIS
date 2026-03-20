# src/core/r9_word_core.py
from __future__ import annotations
from pathlib import Path
import json
import pandas as pd
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

def _load_cfdi_sheet(path: Path) -> pd.DataFrame:
    try: return pd.read_excel(path, sheet_name="CFDI")
    except: return pd.DataFrame()

def _stats(df: pd.DataFrame) -> dict:
    if df.empty: return dict(total=0.0, total_pue=0.0, count=0, count_pue=0)
    mp = df["METODO_PAGO"].astype(str).str.upper()
    total = float(round(df["TOTAL"].sum(), 2))
    pue = df[mp.eq("PUE")]
    total_pue = float(round(pue["TOTAL"].sum(), 2)) if not pue.empty else 0.0
    return dict(total=total, total_pue=total_pue, count=int(len(df)), count_pue=int(len(pue)))

def build_month_summary_docx(exports_dir: Path, rfc: str, yyyy_mm: str) -> Path:
    base = exports_dir / rfc / yyyy_mm
    rec = base / f"{rfc}_{yyyy_mm}_RECIBIDAS_Facturas.xlsx"
    emi = base / f"{rfc}_{yyyy_mm}_EMITIDAS_Facturas.xlsx"
    dfr, dfe = _load_cfdi_sheet(rec), _load_cfdi_sheet(emi)
    s_rec, s_emi = _stats(dfr), _stats(dfe)

    base.mkdir(parents=True, exist_ok=True)
    doc = Document()
    title = doc.add_heading(f"RESUMEN {rfc} {yyyy_mm}", level=1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph("Resumen mensual generado a partir de los Excels CFDI y CFDI_PUE.")
    p.paragraph_format.space_after = Pt(4)

    for rol, st, src in (("RECIBIDAS", s_rec, rec), ("EMITIDAS", s_emi, emi)):
        doc.add_heading(rol, level=2)
        t = doc.add_table(rows=4, cols=2); t.style = "Light List"
        t.cell(0,0).text = "Facturas";       t.cell(0,1).text = str(st["count"])
        t.cell(1,0).text = "Total (TODAS)";  t.cell(1,1).text = f"{st['total']:,.2f}"
        t.cell(2,0).text = "Facturas PUE";   t.cell(2,1).text = str(st["count_pue"])
        t.cell(3,0).text = "Total (PUE)";    t.cell(3,1).text = f"{st['total_pue']:,.2f}"
        doc.add_paragraph(f"Fuente: {src.name if src.exists() else 'No encontrado'}")

    out = base / f"RESUMEN_{rfc}_{yyyy_mm}.docx"
    doc.save(out)
    (base / "manifest.json").write_text(
        json.dumps({"rfc": rfc, "yyyy_mm": yyyy_mm,
                    "files": {"RECIBIDAS": rec.name, "EMITIDAS": emi.name}},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return out
