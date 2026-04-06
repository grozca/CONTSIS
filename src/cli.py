# src/cli.py
import sys
import argparse

USO = """
╔══════════════════════════════════════════════════════╗
║           CONTSIS — Sistema de Robots CFDI           ║
╚══════════════════════════════════════════════════════╝

  PIPELINE COMPLETO (recomendado):
  python -m src.cli pipeline --rfc IIS891106AE6 --year 2025 --month 7

  ROBOTS INDIVIDUALES:
  ── SAT API ──────────────────────────────────────────
  python -m src.cli r0          Bootstrap (valida archivos base)
  python -m src.cli r1          Verificación de certificados
  python -m src.cli r3          Solicitar descarga masiva SAT
  python -m src.cli r4          Verificar estado (todas las solicitudes)
  python -m src.cli r4s         Verificar solo la última solicitud
  python -m src.cli r4id <ID>   Verificar una solicitud específica
  python -m src.cli r5          Descargar paquetes listos

  ── PROCESAMIENTO LOCAL ──────────────────────────────
  python -m src.cli r6          Descomprimir ZIPs y organizar XMLs
  python -m src.cli r6fix       Reorganizar XMLs mal ubicados
  python -m src.cli r7          Organizar estructura de carpetas
  python -m src.cli r7a         Cargar XMLs a base de datos SQLite
  python -m src.cli r8 --rfc RFC --year AAAA --month MM
  python -m src.cli r9 --rfc RFC --yyyy_mm AAAA-MM

  ── ALERTAS ──────────────────────────────────────────
  python -m src.cli alertas           Evaluar y enviar alertas
  python -m src.cli alertas --piloto  Ver alertas sin enviar
"""


def _pipeline(rfc: str, year: int, month: int, solo_local: bool = False):
    """Corre el pipeline completo de procesamiento local."""
    from rich.console import Console
    from rich import print as rprint
    console = Console()

    yyyy_mm = f"{year:04d}-{month:02d}"

    pasos = [
        ("R6  — Descomprimir ZIPs",        "bot_descomprimir",   "run",  []),
        ("R6fix — Reorganizar XMLs",        "bot_fix_reorganizar","run",  []),
        ("R7  — Organizar carpetas",        "bot_organizar",      "run",  []),
        ("R7a — Cargar XMLs a SQLite",      "bot_cargar_xml_a_bd_min", "main", []),
        ("R8  — Exportar Excel",            "bot_export_excel",   "main_rfc", [rfc, year, month]),
        ("R9  — Generar resumen Word",      "bot_export_resumen", "main_rfc", [rfc, yyyy_mm]),
        ("Alertas — Evaluar y notificar",   None,                 "alertas", []),
    ]

    for nombre, modulo, funcion, args in pasos:
        console.rule(f"[bold cyan]{nombre}[/bold cyan]")
        try:
            if modulo == "alertas" or modulo is None:
                import sys, os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'alertas'))
                import alertas as alertas_mod
                alertas_mod.main()
            else:
                mod = __import__(f"src.robots.{modulo}", fromlist=[funcion])
                fn = getattr(mod, funcion if hasattr(mod, funcion) else "run")
                fn(*args) if args else fn()
        except Exception as e:
            console.print(f"[bold red]✗ Error en {nombre}: {e}[/bold red]")
            console.print("[yellow]Continuando con el siguiente paso...[/yellow]")

    console.print("\n[bold green]✅ Pipeline completado[/bold green]")


def main():
    if len(sys.argv) < 2:
        print(USO)
        return

    cmd = sys.argv[1].lower()

    # ── Pipeline completo ──────────────────────────────────────
    if cmd == "pipeline":
        parser = argparse.ArgumentParser()
        parser.add_argument("pipeline")
        parser.add_argument("--rfc",   required=True)
        parser.add_argument("--year",  type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        args = parser.parse_args()
        _pipeline(args.rfc.upper(), args.year, args.month)

    # ── SAT API ───────────────────────────────────────────────
    elif cmd == "r0":
        from src.robots.sat_api import r0_bootstrap
        r0_bootstrap.run()

    elif cmd == "r1":
        from src.robots.sat_api import r1_carga_certs
        r1_carga_certs.run()

    elif cmd == "r3":
        from src.robots.sat_api import r3_solicitar
        r3_solicitar.run()

    elif cmd == "r4":
        from src.robots.sat_api import r4_verificar
        r4_verificar.run()

    elif cmd == "r4s":
        from src.robots.sat_api import r4s_verificar_ultimo
        r4s_verificar_ultimo.run()

    elif cmd == "r4id":
        from src.robots.sat_api import r4id_verificar
        if len(sys.argv) < 3:
            print("Uso: python -m src.cli r4id <IdSolicitud>")
            return
        r4id_verificar.run(sys.argv[2])

    elif cmd == "r5":
        from src.robots.sat_api import r5_descargar
        r5_descargar.run()

    # ── Procesamiento local ───────────────────────────────────
    elif cmd == "r6":
        from src.robots import bot_descomprimir
        bot_descomprimir.run()

    elif cmd == "r6fix":
        from src.robots import bot_fix_reorganizar
        bot_fix_reorganizar.run()

    elif cmd == "r7":
        from src.robots import bot_organizar
        bot_organizar.run()

    elif cmd == "r7a":
        from src.robots import bot_cargar_xml_a_bd_min
        bot_cargar_xml_a_bd_min.main()

    elif cmd == "r8":
        parser = argparse.ArgumentParser()
        parser.add_argument("r8")
        parser.add_argument("--rfc",   required=True)
        parser.add_argument("--year",  type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--roles", default="RECIBIDAS,EMITIDAS")
        args = parser.parse_args()
        from src.robots import bot_export_excel
        # Pasar args directamente
        sys.argv = ["r8", "--rfc", args.rfc,
                    "--year", str(args.year),
                    "--month", str(args.month),
                    "--roles", args.roles]
        bot_export_excel.main()

    elif cmd == "r9":
        parser = argparse.ArgumentParser()
        parser.add_argument("r9")
        parser.add_argument("--rfc",     required=True)
        parser.add_argument("--yyyy_mm", required=True)
        args = parser.parse_args()
        from src.robots import bot_export_resumen
        sys.argv = ["r9", "--rfc", args.rfc, "--yyyy_mm", args.yyyy_mm]
        bot_export_resumen.main()

    # ── Alertas ───────────────────────────────────────────────
    elif cmd == "alertas":
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'alertas'))
        import alertas as alertas_mod
        # Pasar --piloto si se especificó
        if "--piloto" in sys.argv:
            sys.argv = ["alertas", "--piloto"]
        else:
            sys.argv = ["alertas"]
        alertas_mod.main()

    else:
        print(f"Comando desconocido: '{cmd}'")
        print(USO)


if __name__ == "__main__":
    main()