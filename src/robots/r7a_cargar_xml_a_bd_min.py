import sqlite3, sys
from pathlib import Path
import xml.etree.ElementTree as ET

from src.utils.config import settings  # usa tu misma config

def ensure_tables(con):
    con.execute("""
    CREATE TABLE IF NOT EXISTS cfdi (
      uuid TEXT PRIMARY KEY,
      fecha TEXT,
      version TEXT,
      tipo TEXT,
      serie TEXT,
      folio TEXT,
      moneda TEXT,
      tipo_cambio TEXT,
      subtotal REAL,
      descuento REAL,
      total REAL,
      metodo_pago TEXT,
      forma_pago TEXT,
      uso_cfdi TEXT,
      lugar_exp TEXT,
      emisor_rfc TEXT,
      emisor_nombre TEXT,
      receptor_rfc TEXT,
      receptor_nombre TEXT
    );
    """)
    con.commit()

def parse_one(xml_path: Path):
    ns = {"cfdi":"http://www.sat.gob.mx/cfd/4","tfd":"http://www.sat.gob.mx/TimbreFiscalDigital"}
    tree = ET.parse(xml_path)
    root = tree.getroot()
    comp = root
    tfd = root.find(".//tfd:TimbreFiscalDigital", ns)
    uuid = (tfd.get("UUID") if tfd is not None else xml_path.stem).upper()
    fecha = (comp.get("Fecha") or comp.get("fecha") or "")[:19]
    version = comp.get("Version") or comp.get("version")
    tipo = comp.get("TipoDeComprobante") or comp.get("tipoDeComprobante")
    serie = comp.get("Serie") or comp.get("serie")
    folio = comp.get("Folio") or comp.get("folio")
    moneda = comp.get("Moneda") or comp.get("moneda")
    tipo_cambio = comp.get("TipoCambio") or comp.get("tipoCambio")
    subtotal = comp.get("SubTotal") or comp.get("subTotal")
    descuento = comp.get("Descuento") or comp.get("descuento")
    total = comp.get("Total") or comp.get("total")
    metodo_pago = comp.get("MetodoPago") or comp.get("metodoPago")
    forma_pago = comp.get("FormaPago") or comp.get("formaPago")
    uso_cfdi = None
    rc = root.find(".//cfdi:Receptor", ns)
    if rc is not None:
        uso_cfdi = rc.get("UsoCFDI") or rc.get("usoCFDI")
    lugar_exp = comp.get("LugarExpedicion") or comp.get("lugarExpedicion")
    em = root.find(".//cfdi:Emisor", ns)
    emisor_rfc = em.get("Rfc") if em is not None else None
    emisor_nombre = em.get("Nombre") if em is not None else None
    re = rc
    receptor_rfc = re.get("Rfc") if re is not None else None
    receptor_nombre = re.get("Nombre") if re is not None else None

    return (uuid, fecha, version, tipo, serie, folio, moneda, tipo_cambio, subtotal, descuento, total,
            metodo_pago, forma_pago, uso_cfdi, lugar_exp, emisor_rfc, emisor_nombre, receptor_rfc, receptor_nombre)

def upsert_cfdi(con, row):
    con.execute("""
    INSERT INTO cfdi (uuid, fecha, version, tipo, serie, folio, moneda, tipo_cambio, subtotal, descuento, total,
                      metodo_pago, forma_pago, uso_cfdi, lugar_exp, emisor_rfc, emisor_nombre, receptor_rfc, receptor_nombre)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(uuid) DO UPDATE SET
      fecha=excluded.fecha, version=excluded.version, tipo=excluded.tipo,
      serie=excluded.serie, folio=excluded.folio, moneda=excluded.moneda, tipo_cambio=excluded.tipo_cambio,
      subtotal=excluded.subtotal, descuento=excluded.descuento, total=excluded.total,
      metodo_pago=excluded.metodo_pago, forma_pago=excluded.forma_pago, uso_cfdi=excluded.uso_cfdi,
      lugar_exp=excluded.lugar_exp, emisor_rfc=excluded.emisor_rfc, emisor_nombre=excluded.emisor_nombre,
      receptor_rfc=excluded.receptor_rfc, receptor_nombre=excluded.receptor_nombre;
    """, row)

def main():
    # Usa la carpeta donde tus bots dejan los XML organizados
    root = Path("data/boveda/extract")  # si los tienes en otra, cámbiala aquí
    if not root.exists():
        root = Path("data/organizado")   # segunda opción
    if not root.exists():
        print("No encontré carpetas con XML (data/boveda/extract o data/organizado).")
        return

    xmls = list(root.rglob("*.xml"))
    if not xmls:
        print("No encontré XML en las carpetas organizadas.")
        return

    con = sqlite3.connect(settings.db_path)
    ensure_tables(con)
    n=0
    for x in xmls:
        try:
            row = parse_one(x)
            upsert_cfdi(con, row)
            n += 1
        except Exception as e:
            print(f"[WARN] {x}: {e}")
    con.commit()
    con.close()
    print(f"[OK] Cargados/actualizados {n} CFDI en {settings.db_path}")

if __name__ == "__main__":
    main()
