from __future__ import annotations

import logging
import sys
from datetime import date

from .settings import PATHS


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("contsis.alertas_v2")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = logging.FileHandler(PATHS.log_dir / f"alertas_v2_{date.today()}.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    return logger

