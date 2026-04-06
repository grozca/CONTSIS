from __future__ import annotations

import argparse

from app.logging_utils import setup_logging
from app.scheduler_service import run_scheduled_once, run_scheduler_loop


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scheduler del motor de alertas")
    parser.add_argument("--once", action="store_true", help="Evalua si debe correr y ejecuta una sola vez")
    parser.add_argument("--force", action="store_true", help="Fuerza una corrida aunque la ventana no coincida")
    parser.add_argument("--periodo", help="Periodo YYYY-MM a ejecutar manualmente")
    parser.add_argument("--poll-seconds", type=int, default=30, help="Segundos entre revisiones en modo continuo")
    return parser


def main() -> None:
    logger = setup_logging()
    args = build_parser().parse_args()

    if args.once:
        decision = run_scheduled_once(periodo=args.periodo, force=args.force)
        logger.info("Resultado scheduler: %s", decision.reason)
        return

    logger.info("Iniciando scheduler continuo")
    run_scheduler_loop(poll_seconds=args.poll_seconds)


if __name__ == "__main__":
    main()
