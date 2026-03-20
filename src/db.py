# src/utils/db.py
from pathlib import Path
import sqlite3

class DB:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        con = sqlite3.connect(self.db_path)
        con.execute("PRAGMA journal_mode=WAL;")
        return con

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
