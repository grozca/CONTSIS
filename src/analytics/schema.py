from __future__ import annotations

import sqlite3
from pathlib import Path

from runtime_paths import bundle_root, data_path, load_project_env
from src.utils.sqlite_safe import connect_sqlite

load_project_env()
BASE_DIR = bundle_root()
DB_PATH = data_path("db", "analytics.sqlite")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """
    Crea la conexión a SQLite y activa llaves foráneas.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return connect_sqlite(db_path)


def create_tables(conn: sqlite3.Connection) -> None:
    """
    Crea las tablas base de la capa analítica.
    """
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS empresas (
            rfc TEXT PRIMARY KEY,
            razon_social TEXT,
            nombre_corto TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS cfdi (
            uuid TEXT PRIMARY KEY,
            rfc_empresa TEXT NOT NULL,
            periodo TEXT NOT NULL,
            rol TEXT NOT NULL,
            tipo_cfdi TEXT,
            fecha_emision TEXT,
            rfc_emisor TEXT,
            nombre_emisor TEXT,
            rfc_receptor TEXT,
            nombre_receptor TEXT,
            subtotal REAL DEFAULT 0,
            descuento REAL DEFAULT 0,
            total REAL DEFAULT 0,
            moneda TEXT,
            tipo_cambio REAL DEFAULT 1,
            total_mxn REAL DEFAULT 0,
            metodo_pago TEXT,
            forma_pago TEXT,
            uso_cfdi TEXT,
            estatus_cancelado TEXT,
            source_file TEXT,
            ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rfc_empresa) REFERENCES empresas (rfc)
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pagos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uuid_pago TEXT NOT NULL,
            uuid_factura_relacionada TEXT,
            rfc_empresa TEXT NOT NULL,
            periodo TEXT NOT NULL,
            fecha_pago TEXT,
            monto_pago REAL DEFAULT 0,
            moneda TEXT,
            tipo_cambio REAL DEFAULT 1,
            monto_pago_mxn REAL DEFAULT 0,
            rfc_emisor_pago TEXT,
            rfc_receptor_pago TEXT,
            ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rfc_empresa) REFERENCES empresas (rfc)
        );
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS kpis_mensuales_empresa (
            rfc_empresa TEXT NOT NULL,
            periodo TEXT NOT NULL,
            ingresos_mxn REAL DEFAULT 0,
            egresos_mxn REAL DEFAULT 0,
            num_cfdi_emitidos INTEGER DEFAULT 0,
            num_cfdi_recibidos INTEGER DEFAULT 0,
            num_pagos INTEGER DEFAULT 0,
            ticket_promedio_emitido REAL DEFAULT 0,
            ticket_promedio_recibido REAL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (rfc_empresa, periodo),
            FOREIGN KEY (rfc_empresa) REFERENCES empresas (rfc)
        );
        """
    )

    create_indexes(cursor)
    conn.commit()


def create_indexes(cursor: sqlite3.Cursor) -> None:
    """
    Crea índices para acelerar consultas comunes.
    """
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cfdi_rfc_periodo
        ON cfdi (rfc_empresa, periodo);
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cfdi_fecha_emision
        ON cfdi (fecha_emision);
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cfdi_rol
        ON cfdi (rol);
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pagos_rfc_periodo
        ON pagos (rfc_empresa, periodo);
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pagos_uuid_pago
        ON pagos (uuid_pago);
        """
    )


def initialize_database(db_path: Path = DB_PATH) -> None:
    """
    Inicializa la base analítica completa.
    """
    conn = get_connection(db_path)
    try:
        create_tables(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    initialize_database()
    print(f"Base analítica inicializada en: {DB_PATH}")
