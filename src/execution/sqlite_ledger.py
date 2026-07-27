import sqlite3
from datetime import datetime

from loguru import logger

from src.execution.base import BaseActionLedger
from src.models.actions import ActionDispatch


class SQLiteActionLedger(BaseActionLedger):
    """SQLite-backed action ledger."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS action_ledger (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    dispatched_at TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0,
                    outcome TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ledger_session
                ON action_ledger(session_id, dispatched_at)
            """)
            conn.commit()
        logger.info("SQLiteActionLedger initialized")

    async def record(self, dispatch: ActionDispatch) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO action_ledger
                (action_id, session_id, intent, confidence, action, reason,
                 dispatched_at, acknowledged, outcome)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dispatch.action_id,
                    dispatch.session_id,
                    dispatch.intent,
                    dispatch.confidence,
                    dispatch.action,
                    dispatch.reason,
                    dispatch.dispatched_at.isoformat(),
                    int(dispatch.acknowledged),
                    dispatch.outcome,
                ),
            )
            conn.commit()

    async def get_history(self, session_id: str) -> list[ActionDispatch]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM action_ledger WHERE session_id = ? ORDER BY dispatched_at DESC",
                (session_id,),
            ).fetchall()
            return [self._row_to_dispatch(dict(row)) for row in rows]

    async def get_by_id(self, action_id: str) -> ActionDispatch | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM action_ledger WHERE action_id = ?", (action_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_dispatch(dict(row))

    def _row_to_dispatch(self, row: dict) -> ActionDispatch:
        row["dispatched_at"] = datetime.fromisoformat(row["dispatched_at"])
        row["acknowledged"] = bool(row["acknowledged"])
        return ActionDispatch(**row)

    async def close(self) -> None:
        pass
