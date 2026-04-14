from __future__ import annotations

import json
from datetime import datetime

from src.utils.sqlite_safe import connect_sqlite

from .settings import PATHS


class HistorialAlertasRepository:
    def __init__(self, db_path=PATHS.historial_db) -> None:
        self.db_path = db_path

    def init_db(self) -> None:
        with connect_sqlite(self.db_path) as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS historial (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    rfc TEXT,
                    periodo TEXT,
                    modo TEXT,
                    tipo_alerta TEXT,
                    hash_contenido TEXT,
                    fecha_envio TEXT,
                    destinatarios TEXT,
                    estado TEXT
                )
                """
            )
            con.commit()

    def ya_enviado(self, rfc: str, periodo: str, modo: str, hash_contenido: str) -> bool:
        with connect_sqlite(self.db_path) as con:
            row = con.execute(
                "SELECT id FROM historial WHERE rfc=? AND periodo=? AND modo=? AND hash_contenido=? AND estado='ENVIADA'",
                (rfc, periodo, modo, hash_contenido),
            ).fetchone()
        return row is not None

    def registrar_envio(
        self,
        rfc: str,
        periodo: str,
        modo: str,
        hash_contenido: str,
        destinatarios: list[str],
    ) -> None:
        with connect_sqlite(self.db_path) as con:
            con.execute(
                "INSERT INTO historial (rfc, periodo, modo, hash_contenido, fecha_envio, destinatarios, estado) VALUES (?,?,?,?,?,?,?)",
                (
                    rfc,
                    periodo,
                    modo,
                    hash_contenido,
                    datetime.now().isoformat(),
                    json.dumps(destinatarios),
                    "ENVIADA",
                ),
            )
            con.commit()

