# src/utils/db.py
from pathlib import Path

from src.utils.sqlite_safe import connect_sqlite

class DB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        return connect_sqlite(self.db_path)

    def migrate_min(self):
        sql = """
        CREATE TABLE IF NOT EXISTS health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_name TEXT,
            status TEXT,
            details TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS cred_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT,
            rfc TEXT,
            not_before TEXT,
            not_after TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
        with self.connect() as con:
            con.executescript(sql)
