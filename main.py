# main.py
"""
CONTSIS — Punto de entrada principal
Equivalente a: python -m src.cli pipeline ...
Uso rápido desde la raíz sin recordar el módulo completo.

  python main.py --rfc IIS891106AE6 --year 2025 --month 7
  python main.py --rfc ALL --year 2025 --month 8
  python main.py --alertas
  python main.py --alertas --piloto
"""

import sys
import argparse
import os

# Asegura que src/ sea importable desde la raíz
sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(
        description="CONTSIS — Pipeline CFDI completo",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--rfc",    help="RFC a procesar (o ALL para todos)")
    parser.add_argument("--year",   type=int, help="Año (YYYY)")
    parser.add_argument("--month",  type=int, help="Mes (MM)")
    parser.add_argument("--alertas",action="store_true", help="Solo correr alertas")
    parser.add_argument("--piloto", action="store_true", help="Alertas sin enviar notificaciones")
    parser.add_argument("--solo-alertas", action="store_true", help="Saltar pipeline, solo alertas")
    args = parser.parse_args()

    # Modo solo alertas
    if args.alertas or args.solo_alertas:
        _run_alertas(piloto=args.piloto)
        return

    # Modo pipeline completo
    if not all([args.rfc, args.year, args.month]):
        parser.print_help()
        print("\nEjemplo: python main.py --rfc IIS891106AE6 --year 2025 --month 7")
        print("         python main.py --rfc ALL --year 2025 --month 8")
        print("         python main.py --alertas --piloto")
        sys.exit(1)

    rfcs = _resolver_rfcs(args.rfc, args.year, args.month)
    print(f"\n📋 RFCs a procesar: {rfcs}\n")

    for rfc in rfcs:
        print(f"\n{'='*60}")
        print(f"  Procesando RFC: {rfc} — {args.year:04d}-{args.month:02d}")
        print(f"{'='*60}")
        _run_pipeline(rfc, args.year, args.month)

    # Alertas al final de todo
    print(f"\n{'='*60}")
    print("  Evaluando alertas para todos los RFCs procesados")
    print(f"{'='*60}")
    _run_alertas(piloto=args.piloto)


def _resolver_rfcs(rfc_arg: str, year: int, month: int) -> list:
    """Si es ALL, detecta todos los RFCs con ZIPs o XMLs disponibles."""
    if rfc_arg.upper() == "ALL":
        import json
        from pathlib import Path
        config_path = Path("data/config/rfc_names.json")
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            rfcs = [k.strip().upper() for k in data.keys()]
            print(f"[ALL] RFCs encontrados en config: {rfcs}")
            return rfcs
        else:
            print("[ALL] No se encontró data/config/rfc_names.json")
            print("      Crea ese archivo con tus RFCs o especifica uno concreto.")
            sys.exit(1)
    return [rfc_arg.upper()]


def _run_pipeline(rfc: str, year: int, month: int):
    """Corre R6 → R7 → R7a → R8 → R9 para un RFC."""

    pasos = [
        ("R6  — Descomprimir ZIPs",     _r6),
        ("R6fix — Reorganizar XMLs",    _r6fix),
        ("R7  — Organizar carpetas",    _r7),
        ("R7a — Cargar XMLs a SQLite",  _r7a),
        ("R8  — Exportar Excel",        lambda: _r8(rfc, year, month)),
        ("R9  — Generar resumen Word",  lambda: _r9(rfc, year, month)),
    ]

    for nombre, fn in pasos:
        print(f"\n▶ {nombre}...")
        try:
            fn()
            print(f"  ✓ OK")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            print(f"  → Continuando con el siguiente paso...")


def _r6():
    from src.robots import bot_descomprimir
    bot_descomprimir.run()

def _r6fix():
    from src.robots import bot_fix_reorganizar
    bot_fix_reorganizar.run()

def _r7():
    from src.robots import bot_organizar
    bot_organizar.run()

def _r7a():
    from src.robots import bot_cargar_xml_a_bd_min
    bot_cargar_xml_a_bd_min.main()

def _r8(rfc: str, year: int, month: int):
    import sys as _sys
    _sys.argv = ["r8", "--rfc", rfc,
                 "--year", str(year),
                 "--month", str(month),
                 "--roles", "RECIBIDAS,EMITIDAS"]
    from src.robots import bot_export_excel
    bot_export_excel.main()

def _r9(rfc: str, year: int, month: int):
    import sys as _sys
    yyyy_mm = f"{year:04d}-{month:02d}"
    _sys.argv = ["r9", "--rfc", rfc, "--yyyy_mm", yyyy_mm]
    from src.robots import bot_export_resumen
    bot_export_resumen.main()

def _run_alertas(piloto: bool = False):
    import sys as _sys
    import os as _os
    _sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), 'alertas'))
    import alertas as alertas_mod
    _sys.argv = ["alertas", "--piloto"] if piloto else ["alertas"]
    alertas_mod.main()


if __name__ == "__main__":
    main()