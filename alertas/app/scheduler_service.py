from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from .config_validation import validar_config


logger = logging.getLogger("contsis.alertas_v2.scheduler")


WEEKDAY_CODES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True, slots=True)
class SchedulerDecision:
    should_run: bool
    reason: str


def should_run_now(config: dict, now: datetime | None = None) -> SchedulerDecision:
    cfg = validar_config(config).raw
    scheduler_cfg = cfg["scheduler"]
    if not scheduler_cfg["habilitado"]:
        return SchedulerDecision(False, "scheduler deshabilitado")

    tz = ZoneInfo(scheduler_cfg["timezone"])
    local_now = now.astimezone(tz) if now else datetime.now(tz)
    weekday_code = WEEKDAY_CODES[local_now.weekday()]
    if weekday_code not in scheduler_cfg["dias_semana"]:
        return SchedulerDecision(False, f"dia no programado: {weekday_code}")

    hora_actual = local_now.strftime("%H:%M")
    if hora_actual != scheduler_cfg["hora_revision"]:
        return SchedulerDecision(False, f"hora fuera de ventana: {hora_actual}")

    return SchedulerDecision(True, f"ejecutar en {weekday_code} {hora_actual}")


def run_scheduled_once(periodo: str | None = None, force: bool = False) -> SchedulerDecision:
    from .logging_utils import setup_logging
    from .settings import cargar_clientes, cargar_config
    from .storage import HistorialAlertasRepository
    from .use_cases import ejecutar_modo_director

    setup_logging()
    cfg = validar_config(cargar_config()).raw
    clientes = cargar_clientes()
    historial = HistorialAlertasRepository()
    historial.init_db()

    decision = should_run_now(cfg)
    if not force and not decision.should_run:
        logger.info("Scheduler omitido: %s", decision.reason)
        return decision

    tz = ZoneInfo(cfg["scheduler"]["timezone"])
    now = datetime.now(tz)
    if periodo is None:
        periodo = now.strftime("%Y-%m")

    logger.info("Scheduler ejecutando periodo %s", periodo)
    ejecutar_modo_director(periodo, cfg, clientes, piloto=False, forzar=False, historial=historial)
    return SchedulerDecision(True, "ejecucion completada")


def run_scheduler_loop(poll_seconds: int = 30) -> None:
    from .logging_utils import setup_logging
    from .settings import cargar_config

    setup_logging()
    logger.info("Scheduler en ejecucion continua con polling de %s segundos", poll_seconds)
    last_run_key = None
    while True:
        cfg = validar_config(cargar_config()).raw
        tz = ZoneInfo(cfg["scheduler"]["timezone"])
        now = datetime.now(tz)
        run_key = now.strftime("%Y-%m-%d %H:%M")
        decision = should_run_now(cfg, now)
        if decision.should_run and run_key != last_run_key:
            run_scheduled_once(periodo=now.strftime("%Y-%m"))
            last_run_key = run_key
        time.sleep(poll_seconds)
