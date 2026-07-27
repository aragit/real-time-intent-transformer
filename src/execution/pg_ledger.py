import json

import asyncpg
from loguru import logger

from src.execution.base import BaseActionLedger
from src.models.actions import ActionDispatch

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS action_ledger (
    id          BIGSERIAL PRIMARY KEY,
    action_id   TEXT UNIQUE NOT NULL,
    session_id  TEXT NOT NULL,
    action_type TEXT NOT NULL,
    intent      TEXT NOT NULL,
    confidence  DOUBLE PRECISION NOT NULL,
    payload     JSONB DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'dispatched',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ledger_session
    ON action_ledger (session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ledger_action_type
    ON action_ledger (action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ledger_created
    ON action_ledger (created_at DESC);
"""


def _dispatch_to_row(d: ActionDispatch) -> tuple:
    return (
        d.action_id,
        d.session_id,
        d.action,
        d.intent,
        d.confidence,
        json.dumps(
            {
                "reason": d.reason,
                "outcome": d.outcome,
            }
        ),
        "acknowledged" if d.acknowledged else "dispatched",
        d.dispatched_at,
    )


def _row_to_dispatch(row: asyncpg.Record) -> ActionDispatch:
    payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
    return ActionDispatch(
        action_id=row["action_id"],
        session_id=row["session_id"],
        intent=row["intent"],
        confidence=row["confidence"],
        action=row["action_type"],
        reason=payload.get("reason"),
        dispatched_at=row["created_at"],
        acknowledged=(row["status"] == "acknowledged"),
        outcome=payload.get("outcome"),
    )


class PGActionLedger(BaseActionLedger):
    """Async PostgreSQL action ledger backed by asyncpg connection pool."""

    def __init__(self, dsn: str, *, min_size: int = 2, max_size: int = 10):
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
            )
            await self._init_schema()
            logger.info("PGActionLedger pool connected")
        return self._pool

    async def _init_schema(self) -> None:
        pool = self._pool
        if pool is None:
            return
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

    async def record(self, dispatch: ActionDispatch) -> None:
        pool = await self._get_pool()
        row = _dispatch_to_row(dispatch)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO action_ledger
                    (action_id, session_id, action_type, intent, confidence,
                     payload, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                ON CONFLICT (action_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload
                """,
                *row,
            )

    async def get_history(self, session_id: str) -> list[ActionDispatch]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM action_ledger WHERE session_id = $1 ORDER BY created_at DESC",
                session_id,
            )
        return [_row_to_dispatch(r) for r in rows]

    async def get_by_id(self, action_id: str) -> ActionDispatch | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM action_ledger WHERE action_id = $1",
                action_id,
            )
        if row is None:
            return None
        return _row_to_dispatch(row)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
