from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from alertas.app.scheduler_service import should_run_now

from .test_config_validation import build_valid_config


def test_scheduler_runs_inside_window() -> None:
    cfg = build_valid_config()
    now = datetime(2026, 3, 30, 8, 0, tzinfo=ZoneInfo("America/Mexico_City"))
    decision = should_run_now(cfg, now)
    assert decision.should_run is True


def test_scheduler_skips_outside_window() -> None:
    cfg = build_valid_config()
    now = datetime(2026, 3, 30, 9, 0, tzinfo=ZoneInfo("America/Mexico_City"))
    decision = should_run_now(cfg, now)
    assert decision.should_run is False
