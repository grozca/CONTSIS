# src/core/r8_excel_core.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# Esquema exacto y formato
COLUMNS = [
    "RFC_EMISOR","RFC_RECEPTOR","UUID","FECHA","VERSION","TIPO_COMPROB",
    "SERIE","FOLIO","MONEDA","TIPO_CAMBIO","SUBTOTAL","DESCUENTO",
    "SUBTOTAL_MXN","TOTAL_C_D","IVA_16_CALC","TOTAL","METODO_PAGO","FORMA_PAGO",
    "EMISOR_NOMBRE","RECEPTOR_NOMBRE",
]

YELLOW = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
HEADER_FILL = PatternFill(start_color="FFEFE0", end_color="FFEFE0", fill_type="solid")
HEADER_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center", vertical="center")

NS33 = {"cfdi":"http://www.sat.gob.mx/cfd/3", "tfd":"http://www.sat.gob.mx/TimbreFiscalDigital"}
NS40 = {"cfdi":"http://www.sat.gob.mx/cfd/4", "tfd":"http://www.sat.gob.mx/TimbreFiscalDigital"}

def _safe_float(x, default=0.0) -> float:
    try:
        if x in (None, ""): return float(default)
        return float(str(x).replace(",", ""))
    except: return float(default)

def _to_date_str(fecha: str) -> str:
    return (fecha or "")[:10]

def parse_cfdi_bytes(xml_bytes: bytes) -> Dict[str, object]:
    root = ET.fromstring(xml_bytes)
    ns = NS33 if root.tag.endswith("Comprobante") and "cfd/3" in root.tag else NS40
    comp = root

    def ga(names, default=""):
        for n in names:
            if n in comp.attrib: return comp.attrib.get(n, default)
        return default

    version = ga(["Version","version"])
    fecha   = _to_date_str(ga(["Fecha","fecha"]))
    tipo    = (ga(["TipoDeComprobante","tipoDeComprobante","TipoComprobante","tipoComprobante"]) or "").upper()
    serie   = ga(["Serie","serie"])
    folio   = ga(["Folio","folio"])
    moneda  = (ga(["Moneda","moneda"]) or "").upper()
    tc      = ga(["TipoCambio","TipoDeCambio","tipoCambio","tipoDeCambio"])
    subtotal= ga(["SubTotal","subTotal","Subtotal","subtotal"])
    desc    = ga(["Descuento","descuento"], "0")
    mpago   = ga(["MetodoPago","metodoPago"])
    fpago   = ga(["FormaPago","formaPago"])

    em = root.find("cfdi:Emisor", ns); rc = root.find("cfdi:Receptor", ns)
    rfc_em, nom_em = (em.attrib.get("Rfc",""), em.attrib.get("Nombre","")) if em is not None else ("","")
    rfc_rc, nom_rc = (rc.attrib.get("Rfc",""), rc.attrib.get("Nombre","")) if rc is not None else ("","")

    tfd = root.find("cfdi:Complemento/tfd:TimbreFiscalDigital", ns)
    uuid = (tfd.attrib.get("UUID") if tfd is not None else "") or ""

    tc_f = 1.0 if (moneda in ("","MXN")) else _safe_float(tc, 0.0)
    sub_f = _safe_float(subtotal,0.0)
    dsc_f = _safe_float(desc,0.0)
    sub_mxn = sub_f * (tc_f if moneda and moneda!="MXN" else 1.0)
    dsc_mxn = dsc_f * (tc_f if moneda and moneda!="MXN" else 1.0)
    total_cd = sub_mxn - dsc_mxn
    iva = round(total_cd * 0.16, 2)
    total = round(total_cd + iva, 2)

    return {
        "RFC_EMISOR": rfc_em, "RFC_RECEPTOR": rfc_rc, "UUID": uuid, "FECHA": fecha,
        "VERSION": version, "TIPO_COMPROB": tipo, "SERIE": serie, "FOLIO": folio,
        "MONEDA": moneda, "TIPO_CAMBIO": tc_f if moneda and moneda!="MXN" else 1.0,
        "SUBTOTAL": round(sub_f,2), "DESCUENTO": round(dsc_f,2),
        "SUBTOTAL_MXN": round(sub_mxn,2), "TOTAL_C_D": round(total_cd,2),
        "IVA_16_CALC": iva, "TOTAL": total, "METODO_PAGO": mpago, "FORMA_PAGO": fpago,
        "EMISOR_NOMBRE": nom_em, "RECEPTOR_NOMBRE": nom_rc,
    }

def build_monthly_excels_from_xml_bytes(xml_blobs: List[bytes]) -> Dict[str, pd.DataFrame]:
    seen=set(); rows=[]
    for b in xml_blobs:
        try:
            row = parse_cfdi_bytes(b)
            uuid = row.get("UUID","")
            if not uuid or uuid in seen: continue
            seen.add(uuid); rows.append(row)
        except: continue
    df_all = pd.DataFrame(rows, columns=COLUMNS)
    if not df_all.empty:
        df_all = (df_all
                  .assign(FECHA_ORD=df_all["FECHA"].astype(str))
                  .sort_values(["FECHA_ORD","UUID"])
                  .drop(columns=["FECHA_ORD"]))
    df_pue = df_all[df_all["METODO_PAGO"].astype(str).str.upper().eq("PUE")].copy()
    resumen = pd.DataFrame({
        "Concepto": ["Total CFDI (todos)", "Total CFDI_PUE (solo PUE)"],
        "TOTAL": [round(df_all["TOTAL"].sum(),2) if not df_all.empty else 0.0,
                  round(df_pue["TOTAL"].sum(),2) if not df_pue.empty else 0.0],
    })
    return {"CFDI": df_all, "CFDI_PUE": df_pue, "Resumen": resumen}

def save_excels_with_format(sheets: Dict[str, pd.DataFrame], out_path: Path) -> Path:
    from openpyxl import Workbook
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        for name, dfx in sheets.items():
            (dfx if not dfx.empty else dfx.head(0)).to_excel(w, sheet_name=name, index=False)
        wb = w.book  # type: ignore
        for name in ("CFDI","CFDI_PUE","Resumen"):
            if name not in wb.sheetnames: continue
            ws = wb[name]
            # Encabezados + filtros + freeze
            if ws.max_row >= 1:
                for cell in ws[1]:
                    cell.font = HEADER_FONT; cell.fill = HEADER_FILL; cell.alignment = CENTER
                ws.auto_filter.ref = ws.dimensions
                ws.freeze_panes = "A2"
            # Anchos
            for c in range(1, ws.max_column+1):
                col = get_column_letter(c)
                maxlen = max((len(str(cell.value)) if cell.value is not None else 0) for cell in ws[col])
                ws.column_dimensions[col].width = min(max(10, maxlen+2), 42)
            # TOTAL amarillo
            if name in ("CFDI","CFDI_PUE") and "TOTAL" in COLUMNS:
                col_idx = COLUMNS.index("TOTAL")+1
                for r in range(2, ws.max_row+1):
                    ws.cell(row=r, column=col_idx).fill = YELLOW
    return out_path
