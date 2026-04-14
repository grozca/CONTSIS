from __future__ import annotations

import sqlite3
from typing import Any


def compute_kpis_for_company_period(
    cfdi_rows: list[dict[str, Any]],
    pagos_rows: list[dict[str, Any]],
    rfc_empresa: str,
    periodo: str,
) -> dict[str, Any]:
    emitidos = [row for row in cfdi_rows if row.get("rol") == "EMITIDA"]
    recibidos = [row for row in cfdi_rows if row.get("rol") == "RECIBIDA"]

    ingresos_mxn = sum(row.get("total_mxn", 0.0) for row in emitidos if row.get("tipo_cfdi") == "I")
    egresos_mxn = sum(row.get("total_mxn", 0.0) for row in recibidos if row.get("tipo_cfdi") == "I")

    num_cfdi_emitidos = len(emitidos)
    num_cfdi_recibidos = len(recibidos)
    num_pagos = len(pagos_rows)

    ticket_promedio_emitido = ingresos_mxn / num_cfdi_emitidos if num_cfdi_emitidos else 0.0
    ticket_promedio_recibido = egresos_mxn / num_cfdi_recibidos if num_cfdi_recibidos else 0.0

    return {
        "rfc_empresa": rfc_empresa,
        "periodo": periodo,
        "ingresos_mxn": round(ingresos_mxn, 2),
        "egresos_mxn": round(egresos_mxn, 2),
        "num_cfdi_emitidos": num_cfdi_emitidos,
        "num_cfdi_recibidos": num_cfdi_recibidos,
        "num_pagos": num_pagos,
        "ticket_promedio_emitido": round(ticket_promedio_emitido, 2),
        "ticket_promedio_recibido": round(ticket_promedio_recibido, 2),
    }


def upsert_kpis(conn: sqlite3.Connection, kpi_row: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO kpis_mensuales_empresa (
            rfc_empresa,
            periodo,
            ingresos_mxn,
            egresos_mxn,
            num_cfdi_emitidos,
            num_cfdi_recibidos,
            num_pagos,
            ticket_promedio_emitido,
            ticket_promedio_recibido
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(rfc_empresa, periodo) DO UPDATE SET
            ingresos_mxn = excluded.ingresos_mxn,
            egresos_mxn = excluded.egresos_mxn,
            num_cfdi_emitidos = excluded.num_cfdi_emitidos,
            num_cfdi_recibidos = excluded.num_cfdi_recibidos,
            num_pagos = excluded.num_pagos,
            ticket_promedio_emitido = excluded.ticket_promedio_emitido,
            ticket_promedio_recibido = excluded.ticket_promedio_recibido,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            kpi_row["rfc_empresa"],
            kpi_row["periodo"],
            kpi_row["ingresos_mxn"],
            kpi_row["egresos_mxn"],
            kpi_row["num_cfdi_emitidos"],
            kpi_row["num_cfdi_recibidos"],
            kpi_row["num_pagos"],
            kpi_row["ticket_promedio_emitido"],
            kpi_row["ticket_promedio_recibido"],
        ),
    )
