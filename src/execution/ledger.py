import sqlite3
from datetime import datetime
from typing import List, Optional

from loguru import logger

from src.config import settings
from src.models.actions import ActionDispatch


class ActionLedger:
    """Immutable log of every action dispatched."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.database_url.replace("sqlite:///", "")
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
                CREATE INDEX IF NOT EXISTS idx_ledger_session ON action_ledger(session_id, dispatched_at)
            """)
            conn.commit()
        logger.info("ActionLedger initialized")

    def record(self, dispatch: ActionDispatch) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO action_ledger
                (action_id, session_id, intent, confidence, action, reason, dispatched_at, acknowledged, outcome)
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

    def get_history(self, session_id: str) -> List[ActionDispatch]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM action_ledger WHERE session_id = ? ORDER BY dispatched_at DESC",
                (session_id,),
            ).fetchall()
            return [self._row_to_dispatch(dict(row)) for row in rows]

    def _row_to_dispatch(self, row: dict) -> ActionDispatch:
        row["dispatched_at"] = datetime.fromisoformat(row["dispatched_at"])
        row["acknowledged"] = bool(row["acknowledged"])
        return ActionDispatch(**row)
