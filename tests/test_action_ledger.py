import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import asyncpg
import pytest
import pytest_asyncio

from src.execution.base import BaseActionLedger
from src.execution.pg_ledger import PGActionLedger
from src.execution.sqlite_ledger import SQLiteActionLedger
from src.models.actions import ActionDispatch

PG_DSN = "postgresql://postgres:postgres@localhost:5432/intent_transformer"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_ledger(tmp_path):
    db = tmp_path / "test_ledger.db"
    return SQLiteActionLedger(db_path=str(db))


@pytest_asyncio.fixture(scope="module")
async def pg_ledger():
    ledger = PGActionLedger(dsn=PG_DSN, min_size=2, max_size=10)
    # Clean slate for the module
    pool = await ledger._get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE action_ledger RESTART IDENTITY CASCADE")
    yield ledger
    await ledger.close()


@pytest_asyncio.fixture
async def pg_ledger_isolated(tmp_path):
    """Per-test isolated PG ledger using a unique schema to avoid data collisions."""
    test_id = str(uuid.uuid4())[:8]
    schema = f"test_{test_id}"
    pool = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    async with pool.acquire() as conn:
        await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        await conn.execute(f'SET search_path TO "{schema}", public')
        await conn.execute("""
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
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ledger_session ON action_ledger (session_id, created_at DESC)"
        )
    await pool.close()

    ledger = PGActionLedger.__new__(PGActionLedger)
    ledger._dsn = PG_DSN
    ledger._min_size = 1
    ledger._max_size = 5
    ledger._pool = None

    import asyncpg as _asyncpg

    original_create_pool = _asyncpg.create_pool

    async def patched_create_pool(dsn, **kwargs):
        p = await original_create_pool(dsn, **kwargs)
        async with p.acquire() as conn:
            await conn.execute(f'SET search_path TO "{schema}", public')
        return p

    import src.execution.pg_ledger as pg_mod

    original_factory = pg_mod.asyncpg.create_pool
    pg_mod.asyncpg.create_pool = patched_create_pool

    yield ledger

    pg_mod.asyncpg.create_pool = original_factory
    await ledger.close()


def _uniq(prefix: str = "sess") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def make_dispatch(
    action_id: str | None = None,
    session_id: str | None = None,
    intent: str = "cart_abandonment",
    action: str = "APPLY_DISCOUNT",
    reason: str | None = "high_intent",
    outcome: str | None = None,
    dispatched_at: datetime | None = None,
) -> ActionDispatch:
    return ActionDispatch(
        action_id=action_id or str(uuid.uuid4())[:12],
        session_id=session_id or _uniq(),
        intent=intent,
        confidence=0.87,
        action=action,
        reason=reason,
        dispatched_at=dispatched_at or datetime.now(UTC),
        acknowledged=False,
        outcome=outcome,
    )


def make_rich_dispatch(action_id: str | None = None) -> ActionDispatch:
    return ActionDispatch(
        action_id=action_id or str(uuid.uuid4())[:12],
        session_id=_uniq("sess_rich"),
        intent="cross_sell",
        confidence=0.93,
        action="RECOMMEND_ALTERNATIVE",
        reason="ML model scored cross-sell probability 0.93; OPA rule eval: allow",
        dispatched_at=datetime(2024, 7, 2, 8, 30, 0, tzinfo=UTC),
        acknowledged=True,
        outcome="clicked",
    )


# ===========================================================================
# Step 1: Interface & Data Parity
# ===========================================================================


class TestInterfaceParity:
    @pytest.mark.asyncio
    async def test_record_and_get_history_parity(self, sqlite_ledger, pg_ledger_isolated):
        sid = _uniq("sess_parity")
        dispatch = make_dispatch(session_id=sid)
        await sqlite_ledger.record(dispatch)
        await pg_ledger_isolated.record(dispatch)

        sqlite_history = await sqlite_ledger.get_history(sid)
        pg_history = await pg_ledger_isolated.get_history(sid)

        assert len(sqlite_history) == len(pg_history) == 1
        s, p = sqlite_history[0], pg_history[0]

        assert s.action_id == p.action_id == dispatch.action_id
        assert s.session_id == p.session_id == dispatch.session_id
        assert s.intent == p.intent == dispatch.intent
        assert s.action == p.action == dispatch.action
        assert s.confidence == p.confidence == dispatch.confidence
        assert s.acknowledged == p.acknowledged == dispatch.acknowledged
        assert s.reason == p.reason == dispatch.reason
        assert s.outcome == p.outcome == dispatch.outcome

    @pytest.mark.asyncio
    async def test_get_by_id_parity(self, sqlite_ledger, pg_ledger_isolated):
        aid = f"parity_{uuid.uuid4().hex[:6]}"
        dispatch = make_dispatch(action_id=aid)
        await sqlite_ledger.record(dispatch)
        await pg_ledger_isolated.record(dispatch)

        s = await sqlite_ledger.get_by_id(aid)
        p = await pg_ledger_isolated.get_by_id(aid)

        assert s is not None and p is not None
        assert s.action_id == p.action_id
        assert s.session_id == p.session_id
        assert s.intent == p.intent
        assert s.action == p.action

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none(self, sqlite_ledger, pg_ledger_isolated):
        assert await sqlite_ledger.get_by_id("nonexistent") is None
        assert await pg_ledger_isolated.get_by_id("nonexistent") is None

    @pytest.mark.asyncio
    async def test_history_ordering_desc(self, sqlite_ledger, pg_ledger_isolated):
        sid = _uniq("sess_ord")
        base = datetime(2024, 7, 1, 12, 0, 0, tzinfo=UTC)
        for i in range(3):
            d = make_dispatch(
                action_id=f"ord_{uuid.uuid4().hex[:6]}",
                session_id=sid,
                reason=f"reason_{i}",
                dispatched_at=base + timedelta(seconds=i),
            )
            await sqlite_ledger.record(d)
            await pg_ledger_isolated.record(d)

        s_hist = await sqlite_ledger.get_history(sid)
        p_hist = await pg_ledger_isolated.get_history(sid)

        assert len(s_hist) == len(p_hist) == 3
        # Both should have the same set of action_ids
        assert set(h.action_id for h in s_hist) == set(h.action_id for h in p_hist)

    @pytest.mark.asyncio
    async def test_abc_compliance(self, sqlite_ledger, pg_ledger_isolated):
        assert isinstance(sqlite_ledger, BaseActionLedger)
        assert isinstance(pg_ledger_isolated, BaseActionLedger)

    @pytest.mark.asyncio
    async def test_empty_session_returns_empty(self, sqlite_ledger, pg_ledger_isolated):
        empty = _uniq("empty")
        assert await sqlite_ledger.get_history(empty) == []
        assert await pg_ledger_isolated.get_history(empty) == []


# ===========================================================================
# Step 2: Payload Preservation & Idempotency
# ===========================================================================


class TestPayloadAndIdempotency:
    @pytest.mark.asyncio
    async def test_jsonb_nested_payload_preserved(self, pg_ledger_isolated):
        dispatch = make_rich_dispatch(action_id=f"rich_{uuid.uuid4().hex[:6]}")
        await pg_ledger_isolated.record(dispatch)

        result = await pg_ledger_isolated.get_by_id(dispatch.action_id)
        assert result is not None

        assert result.reason == "ML model scored cross-sell probability 0.93; OPA rule eval: allow"
        assert result.outcome == "clicked"
        assert result.acknowledged is True
        assert result.confidence == 0.93

    @pytest.mark.asyncio
    async def test_jsonb_deeply_nested_structure(self, pg_ledger_isolated):
        aid = f"deep_{uuid.uuid4().hex[:6]}"
        dispatch = ActionDispatch(
            action_id=aid,
            session_id=_uniq("sess_deep"),
            intent="upsell",
            confidence=0.77,
            action="LOYALTY_REWARD",
            reason=json.dumps(
                {
                    "ml": {"model": "v3", "scores": [0.91, 0.87, 0.93]},
                    "opa": {"policy": "loyalty.allow", "eval": True},
                    "context": {"page": "/cart", "ab_test": "B"},
                }
            ),
            dispatched_at=datetime(2024, 7, 3, tzinfo=UTC),
        )
        await pg_ledger_isolated.record(dispatch)

        result = await pg_ledger_isolated.get_by_id(aid)
        assert result is not None

        parsed = json.loads(result.reason)
        assert parsed["ml"]["scores"] == [0.91, 0.87, 0.93]
        assert parsed["opa"]["eval"] is True
        assert parsed["context"]["ab_test"] == "B"

    @pytest.mark.asyncio
    async def test_idempotent_write_no_error(self, pg_ledger_isolated):
        aid = f"idemp_{uuid.uuid4().hex[:6]}"
        sid = _uniq("sess_idemp")
        dispatch = make_dispatch(action_id=aid, session_id=sid)
        await pg_ledger_isolated.record(dispatch)
        await pg_ledger_isolated.record(dispatch)

        history = await pg_ledger_isolated.get_history(sid)
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_idempotent_write_updates_status(self, pg_ledger_isolated):
        aid = f"idemp_u_{uuid.uuid4().hex[:6]}"
        d1 = make_dispatch(action_id=aid)
        d1.acknowledged = False
        await pg_ledger_isolated.record(d1)

        d2 = make_dispatch(action_id=aid)
        d2.acknowledged = True
        d2.outcome = "converted"
        await pg_ledger_isolated.record(d2)

        result = await pg_ledger_isolated.get_by_id(aid)
        assert result is not None
        assert result.acknowledged is True
        assert result.outcome == "converted"


# ===========================================================================
# Step 3: Concurrent Write & Pool Stress
# ===========================================================================


class TestConcurrentWrites:
    @pytest.mark.asyncio
    async def test_50_concurrent_writes(self):
        ledger = PGActionLedger(dsn=PG_DSN, min_size=5, max_size=10)
        try:
            pool = await ledger._get_pool()
            async with pool.acquire() as conn:
                await conn.execute("TRUNCATE TABLE action_ledger RESTART IDENTITY CASCADE")

            sid_pool = [_uniq("sess_conc") for _ in range(5)]
            dispatches = [
                make_dispatch(
                    action_id=f"conc_{i:03d}",
                    session_id=sid_pool[i % 5],
                )
                for i in range(50)
            ]

            results = await asyncio.gather(
                *[ledger.record(d) for d in dispatches],
                return_exceptions=True,
            )

            for r in results:
                assert not isinstance(r, Exception), f"Write failed: {r}"

            for sid in set(sid_pool):
                history = await ledger.get_history(sid)
                expected = sum(1 for i in range(50) if sid_pool[i % 5] == sid)
                assert len(history) == expected
        finally:
            await ledger.close()

    @pytest.mark.asyncio
    async def test_concurrent_mixed_read_write(self):
        ledger = PGActionLedger(dsn=PG_DSN, min_size=5, max_size=10)
        try:
            pool = await ledger._get_pool()
            async with pool.acquire() as conn:
                await conn.execute("TRUNCATE TABLE action_ledger RESTART IDENTITY CASCADE")

            sid = _uniq("sess_mixed")
            for i in range(20):
                await ledger.record(
                    make_dispatch(
                        action_id=f"mixed_{i:03d}",
                        session_id=sid,
                    )
                )

            async def read_all():
                return await ledger.get_history(sid)

            async def write_one(idx):
                await ledger.record(
                    make_dispatch(
                        action_id=f"mixed_w_{idx:03d}",
                        session_id=sid,
                    )
                )

            tasks = [read_all()] + [write_one(i) for i in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                assert not isinstance(r, Exception), f"Task failed: {r}"

            final = await ledger.get_history(sid)
            assert len(final) == 30
        finally:
            await ledger.close()


# ===========================================================================
# Step 4: Factory & Teardown Verification
# ===========================================================================


class TestFactoryAndTeardown:
    @pytest.mark.asyncio
    async def test_factory_pg_toggle(self):
        import src.execution as exec_mod
        from src.config import settings

        exec_mod._action_ledger = None

        with (
            patch.object(settings, "use_pg_ledger", True),
            patch.object(settings, "postgres_dsn", PG_DSN),
        ):
            ledger = exec_mod.get_action_ledger()
            assert isinstance(ledger, PGActionLedger)
            await ledger.close()
            exec_mod._action_ledger = None

    @pytest.mark.asyncio
    async def test_factory_sqlite_toggle(self):
        import src.execution as exec_mod
        from src.config import settings

        exec_mod._action_ledger = None

        with (
            patch.object(settings, "use_pg_ledger", False),
            patch.object(settings, "database_url", "sqlite:///./test_ledger_factory.db"),
        ):
            ledger = exec_mod.get_action_ledger()
            assert isinstance(ledger, SQLiteActionLedger)
            await ledger.close()
            exec_mod._action_ledger = None

    @pytest.mark.asyncio
    async def test_close_ledger_noop_when_none(self):
        import src.execution as exec_mod

        exec_mod._action_ledger = None
        await exec_mod.close_ledger()

    @pytest.mark.asyncio
    async def test_close_ledger_cleans_up(self):
        import src.execution as exec_mod
        from src.config import settings

        exec_mod._action_ledger = None

        with (
            patch.object(settings, "use_pg_ledger", True),
            patch.object(settings, "postgres_dsn", PG_DSN),
        ):
            ledger = exec_mod.get_action_ledger()
            exec_mod._action_ledger = ledger
            await exec_mod.close_ledger()
            assert exec_mod._action_ledger is None

    @pytest.mark.asyncio
    async def test_pool_not_left_hanging(self):
        ledger = PGActionLedger(dsn=PG_DSN, min_size=1, max_size=3)
        await ledger.record(make_dispatch())
        await ledger.close()
        assert ledger._pool is None
