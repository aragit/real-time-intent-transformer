import sqlite3
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.config import settings


class SessionStore:
    """SQLite-backed session store with TTL."""

    def __init__(self, db_path: str | None = None):
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

    def upsert(self, session_id: str, customer_id: str | None, ttl_hours: int = 24) -> None:
        now = datetime.now(UTC)
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

    def get(self, session_id: str) -> dict | None:
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
            cur = conn.execute(
                "DELETE FROM sessions WHERE expires_at < ?", (datetime.now(UTC).isoformat(),)
            )
            conn.commit()
            return cur.rowcount
