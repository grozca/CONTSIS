import argparse
import json
import sys
from datetime import datetime


USO = """
CONTSIS - Sistema de Robots CFDI

  PIPELINE COMPLETO:
  python -m src.cli pipeline --rfc IIS891106AE6 --year 2025 --month 7

  SAT API:
  python -m src.cli r0
  python -m src.cli r1
  python -m src.cli r3
  python -m src.cli r4
  python -m src.cli r4s
  python -m src.cli r4id <ID>
  python -m src.cli r5

  PROCESAMIENTO LOCAL:
  python -m src.cli r6
  python -m src.cli r6fix
  python -m src.cli r7
  python -m src.cli r7a   # alias legado de r7
  python -m src.cli r8 --rfc RFC --year AAAA --month MM
  python -m src.cli r9 --rfc RFC --yyyy_mm AAAA-MM

  ALERTAS:
  python -m src.cli alertas --yyyy_mm AAAA-MM
  python -m src.cli alertas --yyyy_mm AAAA-MM --piloto
"""


def _run_alertas(yyyy_mm: str, piloto: bool = False, forzar: bool = False) -> None:
    from alertas import alertas_v2 as alertas_mod

    original_argv = sys.argv[:]
    try:
        sys.argv = ["alertas_v2", "--yyyy_mm", yyyy_mm]
        if piloto:
            sys.argv.append("--piloto")
        if forzar:
            sys.argv.append("--forzar")
        alertas_mod.main()
    finally:
        sys.argv = original_argv


def _run_robot_main(modulo: str, argv: list[str]) -> None:
    mod = __import__(f"src.robots.{modulo}", fromlist=["main"])
    original_argv = sys.argv[:]
    try:
        sys.argv = argv
        mod.main()
    finally:
        sys.argv = original_argv


def _pipeline(rfc: str, year: int, month: int) -> None:
    from rich.console import Console

    console = Console()
    yyyy_mm = f"{year:04d}-{month:02d}"
    pasos = [
        ("R6 - Descomprimir ZIPs", lambda: __import__("src.robots.bot_descomprimir", fromlist=["run"]).run()),
        ("R6fix - Reorganizar XMLs", lambda: __import__("src.robots.bot_fix_reorganizar", fromlist=["run"]).run()),
        ("R7 - Cargar XMLs a SQLite", lambda: __import__("src.robots.bot_cargar_xml_a_bd_min", fromlist=["main"]).main()),
        (
            "R8 - Exportar Excel",
            lambda: _run_robot_main(
                "bot_export_excel",
                ["r8", "--rfc", rfc, "--year", str(year), "--month", str(month), "--roles", "RECIBIDAS,EMITIDAS"],
            ),
        ),
        (
            "Analytics - Refrescar dashboard",
            lambda: _refresh_analytics(yyyy_mm),
        ),
        (
            "R9 - Generar resumen Word",
            lambda: _run_robot_main("bot_export_resumen", ["r9", "--rfc", rfc, "--yyyy_mm", yyyy_mm]),
        ),
        ("Alertas - Evaluar y notificar", lambda: _run_alertas(yyyy_mm, piloto=False)),
    ]

    for nombre, funcion in pasos:
        console.rule(f"[bold cyan]{nombre}[/bold cyan]")
        try:
            funcion()
        except Exception as exc:
            console.print(f"[bold red]Error en {nombre}: {exc}[/bold red]")
            console.print("[yellow]Continuando con el siguiente paso...[/yellow]")

    console.print("\n[bold green]Pipeline completado[/bold green]")


def main() -> None:
    if len(sys.argv) < 2:
        print(USO)
        return

    cmd = sys.argv[1].lower()

    if cmd == "pipeline":
        parser = argparse.ArgumentParser()
        parser.add_argument("pipeline")
        parser.add_argument("--rfc", required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        args = parser.parse_args()
        _pipeline(args.rfc.upper(), args.year, args.month)
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
    elif cmd == "r6":
        from src.robots import bot_descomprimir

        bot_descomprimir.run()
    elif cmd == "r6fix":
        from src.robots import bot_fix_reorganizar

        bot_fix_reorganizar.run()
    elif cmd in {"r7", "r7a"}:
        from src.robots import bot_cargar_xml_a_bd_min

        bot_cargar_xml_a_bd_min.main()
    elif cmd == "r8":
        parser = argparse.ArgumentParser()
        parser.add_argument("r8")
        parser.add_argument("--rfc", required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--month", type=int, required=True)
        parser.add_argument("--roles", default="RECIBIDAS,EMITIDAS")
        args = parser.parse_args()
        _run_robot_main(
            "bot_export_excel",
            ["r8", "--rfc", args.rfc, "--year", str(args.year), "--month", str(args.month), "--roles", args.roles],
        )
        _refresh_analytics(f"{args.year:04d}-{args.month:02d}")
    elif cmd == "r9":
        parser = argparse.ArgumentParser()
        parser.add_argument("r9")
        parser.add_argument("--rfc", required=True)
        parser.add_argument("--yyyy_mm", required=True)
        args = parser.parse_args()
        _run_robot_main("bot_export_resumen", ["r9", "--rfc", args.rfc, "--yyyy_mm", args.yyyy_mm])
    elif cmd == "alertas":
        parser = argparse.ArgumentParser()
        parser.add_argument("alertas")
        parser.add_argument("--yyyy_mm", required=False)
        parser.add_argument("--piloto", action="store_true")
        parser.add_argument("--forzar", action="store_true")
        args = parser.parse_args()
        periodo = args.yyyy_mm or datetime.now().strftime("%Y-%m")
        _run_alertas(periodo, piloto=args.piloto, forzar=args.forzar)
    else:
        print(f"Comando desconocido: '{cmd}'")
        print(USO)


def _refresh_analytics(periodo: str) -> None:
    from src.analytics.build_monthly import build_monthly

    summary = build_monthly(periodo)
    print(json.dumps({"analytics_refreshed": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
