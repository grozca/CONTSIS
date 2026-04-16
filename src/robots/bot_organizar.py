# src/robots/r7_organizar.py
# LEGACY: este bot pertenecia a una estructura anterior con carpeta `organizado`.
# Ya no forma parte del pipeline principal; se conserva solo para compatibilidad puntual.
import logging
from pathlib import Path
import shutil
from src.utils.config import settings

log = logging.getLogger(__name__)

def run():
    """
    Organiza los XML ya descomprimidos en carpetas por RFC / año-mes / (Emitidas|Recibidas).
    """
    base_extract = Path(settings.boveda_dir) / "extract"
    base_target = Path(settings.organized_dir)
    base_target.mkdir(parents=True, exist_ok=True)

    moved = 0
    for folder in base_extract.iterdir():
        if not folder.is_dir():
            continue

        for xml in folder.glob("*.xml"):
            try:
                rfc = None
                if "EMITIDAS" in folder.name.upper():
                    tipo = "Emitidas"
                else:
                    tipo = "Recibidas"

                # RFC detectado del nombre de carpeta padre o filename
                parts = folder.name.split("_")
                for p in parts:
                    if len(p) == 13:  # RFC típico de 13 caracteres
                        rfc = p
                        break
                if not rfc:
                    rfc = settings.rfc or "RFC"

                # Año-mes desde nombre carpeta si existe
                ym = next((p for p in parts if p.isdigit() and len(p) == 6), None)
                ym = ym or "000000"

                dest_dir = base_target / rfc / ym / tipo
                dest_dir.mkdir(parents=True, exist_ok=True)

                shutil.copy2(xml, dest_dir / xml.name)
                moved += 1
            except Exception as e:
                log.error("Error moviendo %s: %s", xml, e)

    log.info("R7: Organizados %d XML en carpetas RFC/año-mes/tipo", moved)
    print(f"R7: Organizados {moved} XML")
