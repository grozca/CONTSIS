"""
CONTSIS - Punto de entrada principal.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, os.path.dirname(__file__))
from src.utils.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CONTSIS - Pipeline CFDI completo",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--rfc", help="RFC a procesar (o ALL para todos)")
    parser.add_argument("--year", type=int, help="Anio (YYYY)")
    parser.add_argument("--month", type=int, help="Mes (MM)")
    parser.add_argument("--alertas", action="store_true", help="Solo correr alertas")
    parser.add_argument("--piloto", action="store_true", help="Alertas sin enviar notificaciones")
    parser.add_argument("--solo-alertas", action="store_true", help="Saltar pipeline, solo alertas")
    args = parser.parse_args()

    if args.alertas or args.solo_alertas:
        _run_alertas(piloto=args.piloto)
        return

    if not all([args.rfc, args.year, args.month]):
        parser.print_help()
        print("\nEjemplo: python main.py --rfc IIS891106AE6 --year 2025 --month 7")
        print("         python main.py --rfc ALL --year 2025 --month 8")
        print("         python main.py --alertas --piloto")
        sys.exit(1)

    rfcs = _resolver_rfcs(args.rfc)
    print(f"\nRFCs a procesar: {rfcs}\n")

    for rfc in rfcs:
        print(f"\n{'=' * 60}")
        print(f"  Procesando RFC: {rfc} - {args.year:04d}-{args.month:02d}")
        print(f"{'=' * 60}")
        _run_pipeline(rfc, args.year, args.month)

    print(f"\n{'=' * 60}")
    print("  Evaluando alertas para todos los RFCs procesados")
    print(f"{'=' * 60}")
    _run_alertas(piloto=args.piloto)


def _resolver_rfcs(rfc_arg: str) -> list[str]:
    if rfc_arg.upper() != "ALL":
        return [rfc_arg.upper()]

    config_candidates = [
        settings.rfc_names_path,
        settings.rfc_names_example_path,
    ]
    for config_path in config_candidates:
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            rfcs = [key.strip().upper() for key in data.keys()]
            if rfcs:
                print(f"[ALL] RFCs encontrados en config: {rfcs}")
                return rfcs

    extract_dir = Path(settings.boveda_dir) / "extract"
    if extract_dir.exists():
        rfcs = sorted(path.name.upper() for path in extract_dir.iterdir() if path.is_dir())
        if rfcs:
            print(f"[ALL] RFCs detectados en boveda: {rfcs}")
            return rfcs

    print(f"[ALL] No se encontro configuracion de RFCs ni carpetas en {extract_dir}")
    print("      Crea data/config/rfc_names.json o especifica un RFC concreto.")
    sys.exit(1)


def _run_pipeline(rfc: str, year: int, month: int) -> None:
    pasos = [
        ("R6  - Descomprimir ZIPs", _r6),
        ("R6fix - Reorganizar XMLs", _r6fix),
        ("R7  - Organizar carpetas", _r7),
        ("R7a - Cargar XMLs a SQLite", _r7a),
        ("R8  - Exportar Excel", lambda: _r8(rfc, year, month)),
        ("R9  - Generar resumen Word", lambda: _r9(rfc, year, month)),
    ]

    for nombre, funcion in pasos:
        print(f"\n> {nombre}...")
        try:
            funcion()
            print("  OK")
        except Exception as exc:
            print(f"  Error: {exc}")
            print("  Continuando con el siguiente paso...")


def _r6() -> None:
    from src.robots import bot_descomprimir

    bot_descomprimir.run()


def _r6fix() -> None:
    from src.robots import bot_fix_reorganizar

    bot_fix_reorganizar.run()


def _r7() -> None:
    from src.robots import bot_organizar

    bot_organizar.run()


def _r7a() -> None:
    from src.robots import bot_cargar_xml_a_bd_min

    bot_cargar_xml_a_bd_min.main()


def _r8(rfc: str, year: int, month: int) -> None:
    import sys as _sys
    from src.robots import bot_export_excel

    original_argv = _sys.argv[:]
    try:
        _sys.argv = ["r8", "--rfc", rfc, "--year", str(year), "--month", str(month), "--roles", "RECIBIDAS,EMITIDAS"]
        bot_export_excel.main()
    finally:
        _sys.argv = original_argv


def _r9(rfc: str, year: int, month: int) -> None:
    import sys as _sys
    from src.robots import bot_export_resumen

    yyyy_mm = f"{year:04d}-{month:02d}"
    original_argv = _sys.argv[:]
    try:
        _sys.argv = ["r9", "--rfc", rfc, "--yyyy_mm", yyyy_mm]
        bot_export_resumen.main()
    finally:
        _sys.argv = original_argv


def _run_alertas(piloto: bool = False) -> None:
    import sys as _sys
    from alertas import alertas_v2 as alertas_mod

    periodo = datetime.now().strftime("%Y-%m")

    original_argv = _sys.argv[:]
    try:
        _sys.argv = ["alertas_v2", "--yyyy_mm", periodo]
        if piloto:
            _sys.argv.append("--piloto")
        alertas_mod.main()
    finally:
        _sys.argv = original_argv


if __name__ == "__main__":
    main()
