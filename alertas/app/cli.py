from __future__ import annotations

import argparse

from .config_validation import validar_config
from .logging_utils import setup_logging
from .settings import cargar_clientes, cargar_config
from .storage import HistorialAlertasRepository
from .use_cases import ejecutar_modo_cliente, ejecutar_modo_director


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CONTSIS Motor de Alertas v2.0")
    parser.add_argument("--yyyy_mm", required=True, help="Periodo a analizar (ej. 2026-03)")
    parser.add_argument(
        "--modo",
        default="director",
        choices=["director", "cliente"],
        help="director = resumen ejecutivo | cliente = reporte mensual al cliente",
    )
    parser.add_argument("--rfc", help="RFC especifico (requerido en modo cliente)")
    parser.add_argument("--piloto", action="store_true", help="Ver alertas sin enviar correo")
    parser.add_argument("--forzar", action="store_true", help="Reenviar aunque ya se haya mandado")
    return parser


def main() -> None:
    logger = setup_logging()
    historial = HistorialAlertasRepository()
    historial.init_db()

    parser = build_parser()
    args = parser.parse_args()
    cfg = validar_config(cargar_config()).raw
    clientes = cargar_clientes()

    logger.info("=" * 60)
    logger.info("CONTSIS Alertas v2.0 - %s - modo %s", args.yyyy_mm, args.modo)
    logger.info("=" * 60)

    if args.modo == "cliente":
        if not args.rfc:
            parser.error("--rfc es requerido en modo cliente")
        ejecutar_modo_cliente(args.rfc.upper(), args.yyyy_mm, cfg, clientes, args.piloto, args.forzar, historial)
    else:
        ejecutar_modo_director(args.yyyy_mm, cfg, clientes, args.piloto, args.forzar, historial)

    logger.info("Finalizado.")
