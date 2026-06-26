import sqlite3
from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class EventStore:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_url.replace("sqlite:///", "")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    customer_id TEXT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    product_id TEXT,
                    category TEXT,
                    value REAL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session ON events(session_id, timestamp)
            """)
            conn.commit()
        logger.info(f"EventStore initialized: {self.db_path}")

    def insert(self, event: ClickEvent) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO events
                (event_id, session_id, customer_id, timestamp, action, product_id, category, value, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.customer_id,
                    event.timestamp.isoformat(),
                    event.action,
                    event.product_id,
                    event.category,
                    event.value,
                    str(event.metadata) if event.metadata else "{}",
                ),
            )
            conn.commit()

    def get_session_events(self, session_id: str) -> List[ClickEvent]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
                (session_id,),
            ).fetchall()
            return [self._row_to_event(dict(row)) for row in rows]

    def _row_to_event(self, row: dict) -> ClickEvent:
        row["timestamp"] = datetime.fromisoformat(row["timestamp"])
        row["metadata"] = eval(row["metadata"]) if row["metadata"] else {}
        return ClickEvent(**row)
