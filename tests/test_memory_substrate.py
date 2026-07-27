import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import fakeredis.aioredis
import pytest
import pytest_asyncio

from src.memory.base import BaseEventStore, BaseSessionStore
from src.memory.redis_store import RedisEventStore, RedisSessionStore
from src.memory.sqlite_store import SQLiteEventStore, SQLiteSessionStore
from src.models.events import ClickEvent

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_session_store(tmp_path):
    db = tmp_path / "test_sessions.db"
    return SQLiteSessionStore(db_path=str(db))


@pytest.fixture
def sqlite_event_store(tmp_path):
    db = tmp_path / "test_events.db"
    return SQLiteEventStore(db_path=str(db))


@pytest_asyncio.fixture
async def redis_client():
    client = fakeredis.aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def redis_session_store(redis_client):
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._redis_url = "redis://localhost:6379/0"
    store._client = redis_client
    yield store
    await store.close()


@pytest_asyncio.fixture
async def redis_event_store(redis_client):
    store = RedisEventStore.__new__(RedisEventStore)
    store._redis_url = "redis://localhost:6379/0"
    store._client = redis_client
    yield store
    await store.close()


@pytest.fixture
def sample_session():
    return {
        "session_id": "sess_test_001",
        "customer_id": "cust_001",
        "ttl_hours": 24,
    }


@pytest.fixture
def sample_event():
    return ClickEvent(
        session_id="sess_test_001",
        customer_id="cust_001",
        timestamp=datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
        action="page_view",
        product_id="prod_100",
        category="electronics",
        value=None,
        metadata={"source": "homepage"},
    )


def make_event(index: int, session_id: str = "sess_bulk") -> ClickEvent:
    return ClickEvent(
        session_id=session_id,
        customer_id="cust_bulk",
        timestamp=datetime(2024, 6, 15, 10, 0, 0, tzinfo=UTC) + timedelta(seconds=index),
        action="page_view",
        product_id=f"prod_{index}",
        category="misc",
        value=float(index),
        metadata={"seq": index},
    )


# ===========================================================================
# Step 1: Interface & Data Parity Tests
# ===========================================================================


class TestInterfaceParity:
    """Both backends must produce identical dict structures for sessions."""

    @pytest.mark.asyncio
    async def test_upsert_get_parity(
        self, sqlite_session_store, redis_session_store, sample_session
    ):
        sid = sample_session["session_id"]
        cid = sample_session["customer_id"]
        ttl = sample_session["ttl_hours"]

        await sqlite_session_store.upsert(sid, cid, ttl)
        await redis_session_store.upsert(sid, cid, ttl)

        sqlite_row = await sqlite_session_store.get(sid)
        redis_row = await redis_session_store.get(sid)

        assert sqlite_row is not None, "SQLite returned None"
        assert redis_row is not None, "Redis returned None"

        # Core keys present in both
        expected_keys = {"session_id", "customer_id", "created_at", "last_activity", "expires_at"}
        assert set(sqlite_row.keys()) >= expected_keys
        assert set(redis_row.keys()) >= expected_keys

        # Type parity
        for key in expected_keys:
            assert type(sqlite_row[key]) is type(redis_row[key]), f"Type mismatch on {key}"

        # Value parity (session_id and customer_id must match exactly)
        assert sqlite_row["session_id"] == redis_row["session_id"] == sid
        assert sqlite_row["customer_id"] == redis_row["customer_id"] == cid

    @pytest.mark.asyncio
    async def test_upsert_get_none_parity(self, sqlite_session_store, redis_session_store):
        assert await sqlite_session_store.get("nonexistent") is None
        assert await redis_session_store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_event_insert_get_parity(
        self, sqlite_event_store, redis_event_store, sample_event
    ):
        await sqlite_event_store.insert(sample_event)
        await redis_event_store.insert(sample_event)

        sqlite_events = await sqlite_event_store.get_session_events(sample_event.session_id)
        redis_events = await redis_event_store.get_session_events(sample_event.session_id)

        assert len(sqlite_events) == len(redis_events) == 1

        se, re = sqlite_events[0], redis_events[0]
        assert se.event_id == re.event_id
        assert se.session_id == re.session_id
        assert se.action == re.action
        assert se.product_id == re.product_id
        assert se.category == re.category
        assert se.metadata == re.metadata

    @pytest.mark.asyncio
    async def test_abc_contract_compliance(self, sqlite_session_store, sqlite_event_store):
        assert isinstance(sqlite_session_store, BaseSessionStore)
        assert isinstance(sqlite_event_store, BaseEventStore)


# ===========================================================================
# Step 2: Boundary & TTL Enforcement
# ===========================================================================


class TestBoundaryBehavior:
    @pytest.mark.asyncio
    async def test_bounded_event_stream_ltrim(self, redis_event_store):
        """Push 120 events; only the latest 100 should survive LTRIM."""
        session_id = "sess_bulk"
        for i in range(120):
            await redis_event_store.insert(make_event(i, session_id))

        events = await redis_event_store.get_session_events(session_id)
        assert len(events) == 100

        # First retained event should be seq 20 (0-indexed), last should be 119
        assert events[0].metadata["seq"] == 20
        assert events[-1].metadata["seq"] == 119

    @pytest.mark.asyncio
    async def test_session_ttl_attached(self, redis_session_store, redis_client):
        """Redis key must have a TTL set after upsert."""
        await redis_session_store.upsert("sess_ttl", "cust_ttl", ttl_hours=2)
        ttl_val = await redis_client.ttl("session:sess_ttl")
        assert ttl_val > 0, f"Expected positive TTL, got {ttl_val}"
        assert ttl_val <= 2 * 3600

    @pytest.mark.asyncio
    async def test_session_expires_returns_none(self, redis_session_store, redis_client):
        """Manually expire a key; get() must return None."""
        await redis_session_store.upsert("sess_expire", "cust_e", ttl_hours=1)
        await redis_client.set(
            "session:sess_expire",
            json.dumps(
                {
                    "session_id": "sess_expire",
                    "customer_id": "cust_e",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "last_activity": "2024-01-01T00:00:00+00:00",
                    "expires_at": "2020-01-01T00:00:00+00:00",  # already expired
                }
            ),
        )
        result = await redis_session_store.get("sess_expire")
        assert result is None

    @pytest.mark.asyncio
    async def test_bounded_stream_preserves_order(self, redis_event_store):
        """Events must come back in chronological order after trimming."""
        session_id = "sess_order"
        for i in range(105):
            await redis_event_store.insert(make_event(i, session_id))

        events = await redis_event_store.get_session_events(session_id)
        timestamps = [e.timestamp for e in events]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_delete_expired_sqlite(self, sqlite_session_store):
        """SQLite delete_expired must remove old rows and return count."""
        await sqlite_session_store.upsert("s1", "c1", ttl_hours=0)
        await sqlite_session_store.upsert("s2", "c2", ttl_hours=999)
        deleted = await sqlite_session_store.delete_expired()
        assert deleted >= 1


# ===========================================================================
# Step 3: Factory & Teardown Verification
# ===========================================================================


class TestFactoryAndTeardown:
    @pytest.mark.asyncio
    async def test_factory_redis_toggle(self):
        import src.memory as mem_mod
        from src.config import settings

        mem_mod._session_store = None
        mem_mod._event_store = None

        with (
            patch.object(settings, "use_redis_store", True),
            patch.object(settings, "redis_url", "redis://localhost:6379/0"),
        ):
            store = mem_mod.get_session_store()
            assert isinstance(store, RedisSessionStore)
            await store.close()
            mem_mod._session_store = None

    @pytest.mark.asyncio
    async def test_factory_sqlite_toggle(self):
        import src.memory as mem_mod
        from src.config import settings

        mem_mod._session_store = None
        mem_mod._event_store = None

        with (
            patch.object(settings, "use_redis_store", False),
            patch.object(settings, "database_url", "sqlite:///./test_factory.db"),
        ):
            store = mem_mod.get_session_store()
            assert isinstance(store, SQLiteSessionStore)
            await store.close()
            mem_mod._session_store = None

    @pytest.mark.asyncio
    async def test_close_stores_noop_when_none(self):
        import src.memory as mem_mod

        mem_mod._session_store = None
        mem_mod._event_store = None
        await mem_mod.close_stores()

    @pytest.mark.asyncio
    async def test_close_stores_cleans_up(self, redis_session_store, redis_event_store):
        import src.memory as mem_mod

        mem_mod._session_store = redis_session_store
        mem_mod._event_store = redis_event_store
        await mem_mod.close_stores()
        assert mem_mod._session_store is None
        assert mem_mod._event_store is None
