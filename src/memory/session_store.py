import sqlite3
from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class SessionStore:
    """SQLite-backed session store with TTL."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_url.replace("sqlite:///", "")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    created_at TEXT NOT NULL,
                    last_activity TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.commit()
        logger.info("SessionStore initialized")

    def upsert(self, session_id: str, customer_id: Optional[str], ttl_hours: int = 24) -> None:
        now = datetime.utcnow()
        expires = now + timedelta(hours=ttl_hours)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (session_id, customer_id, created_at, last_activity, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    last_activity = excluded.last_activity,
                    expires_at = excluded.expires_at
                """,
                (session_id, customer_id, now.isoformat(), now.isoformat(), expires.isoformat()),
            )
            conn.commit()

    def get(self, session_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def delete_expired(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (datetime.utcnow().isoformat(),))
            conn.commit()
            return cur.rowcount
