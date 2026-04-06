from __future__ import annotations

import sys
from pathlib import Path


TESTS_DIR = Path(__file__).resolve().parent
ALERTAS_DIR = TESTS_DIR.parent

if str(ALERTAS_DIR) not in sys.path:
    sys.path.insert(0, str(ALERTAS_DIR))
