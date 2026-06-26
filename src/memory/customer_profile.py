import sqlite3
from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.config import settings
from src.models.customer import CustomerProfile
from src.models.intent import IntentPrediction


class CustomerProfileStore:
    """Aggregated customer behavior storage."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_url.replace("sqlite:///", "")
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customer_id TEXT PRIMARY KEY,
                    total_sessions INTEGER DEFAULT 0,
                    total_purchases INTEGER DEFAULT 0,
                    lifetime_value REAL DEFAULT 0.0,
                    avg_session_duration REAL DEFAULT 0.0,
                    preferred_categories TEXT,
                    last_updated TEXT NOT NULL
                )
            """)
            conn.commit()
        logger.info("CustomerProfileStore initialized")

    def upsert(self, profile: CustomerProfile) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO customers
                (customer_id, total_sessions, total_purchases, lifetime_value, avg_session_duration, preferred_categories, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(customer_id) DO UPDATE SET
                    total_sessions = excluded.total_sessions,
                    total_purchases = excluded.total_purchases,
                    lifetime_value = excluded.lifetime_value,
                    avg_session_duration = excluded.avg_session_duration,
                    preferred_categories = excluded.preferred_categories,
                    last_updated = excluded.last_updated
                """,
                (
                    profile.customer_id,
                    profile.total_sessions,
                    profile.total_purchases,
                    profile.lifetime_value,
                    profile.avg_session_duration,
                    ",".join(profile.preferred_categories),
                    profile.last_updated.isoformat(),
                ),
            )
            conn.commit()

    def get(self, customer_id: str) -> Optional[CustomerProfile]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM customers WHERE customer_id = ?", (customer_id,)
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["preferred_categories"] = data["preferred_categories"].split(",") if data["preferred_categories"] else []
            data["intent_history"] = []  # Loaded separately if needed
            data["last_updated"] = datetime.fromisoformat(data["last_updated"])
            return CustomerProfile(**data)
