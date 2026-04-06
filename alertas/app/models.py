from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass(slots=True)
class ClientPeriodData:
    rfc: str
    periodo: str
    df_e: pd.DataFrame
    df_r: pd.DataFrame

    @property
    def tiene_e(self) -> bool:
        return not self.df_e.empty

    @property
    def tiene_r(self) -> bool:
        return not self.df_r.empty


@dataclass(slots=True)
class Alert:
    rfc: str
    nombre: str
    periodo: str
    tipo_alerta: str
    severidad: str
    resumen: str
    detalle: str
    cantidad: int = 1
    monto_total: float = 0.0
    uuids: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_history_payload(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo_alerta,
            "rfc": self.rfc,
            "cantidad": self.cantidad,
            "monto": self.monto_total,
        }

