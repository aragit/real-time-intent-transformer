import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.memory.base import BaseEventStore, BaseSessionStore
from src.models.events import ClickEvent


class SQLiteSessionStore(BaseSessionStore):
    """SQLite-backed session store with TTL."""

    def __init__(self, db_path: str):
        self.db_path = db_path
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
        logger.info("SQLiteSessionStore initialized")

    async def upsert(self, session_id: str, customer_id: str | None, ttl_hours: int = 24) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(hours=ttl_hours)

        def _sync_upsert():
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

        await asyncio.to_thread(_sync_upsert)

    async def get(self, session_id: str) -> dict | None:
        def _sync_get() -> dict | None:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()
                if not row:
                    return None
                return dict(row)

        session = await asyncio.to_thread(_sync_get)
        if session and datetime.fromisoformat(session["expires_at"]) < datetime.now(UTC):
            await self._delete(session_id)
            return None
        return session

    async def _delete(self, session_id: str) -> None:
        def _sync_delete():
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()

        await asyncio.to_thread(_sync_delete)

    async def delete_expired(self) -> int:
        def _sync_delete_expired() -> int:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute(
                    "DELETE FROM sessions WHERE expires_at < ?",
                    (datetime.now(UTC).isoformat(),),
                )
                conn.commit()
                return cur.rowcount

        return await asyncio.to_thread(_sync_delete_expired)

    async def close(self) -> None:
        pass


class SQLiteEventStore(BaseEventStore):
    """SQLite-backed event store."""

    def __init__(self, db_path: str):
        self.db_path = db_path
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
        logger.info(f"SQLiteEventStore initialized: {self.db_path}")

    async def insert(self, event: ClickEvent) -> None:
        def _sync_insert():
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
                        json.dumps(event.metadata) if event.metadata else "{}",
                    ),
                )
                conn.commit()

        await asyncio.to_thread(_sync_insert)

    async def get_session_events(self, session_id: str) -> list[ClickEvent]:
        def _sync_get_events() -> list[ClickEvent]:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM events WHERE session_id = ? ORDER BY timestamp",
                    (session_id,),
                ).fetchall()
                return [self._row_to_event(dict(row)) for row in rows]

        return await asyncio.to_thread(_sync_get_events)

    def _row_to_event(self, row: dict) -> ClickEvent:
        return ClickEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            customer_id=row.get("customer_id"),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            action=row["action"],
            product_id=row.get("product_id"),
            category=row.get("category"),
            value=row.get("value"),
            metadata=json.loads(row.get("metadata", "{}")),
        )

    async def delete_expired_events(self, ttl_hours: int = 24) -> int:
        """Prune events older than ttl_hours to prevent unbounded table growth."""
        cutoff = (datetime.now(UTC) - timedelta(hours=ttl_hours)).isoformat()

        def _sync_delete_expired() -> int:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
                conn.commit()
                return cur.rowcount

        return await asyncio.to_thread(_sync_delete_expired)

    async def close(self) -> None:
        pass
