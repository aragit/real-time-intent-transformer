from datetime import datetime

from src.ingestion.event_store import EventStore
from src.models.events import ClickEvent


class TestEventStore:
    def test_insert_and_retrieve(self, tmp_path, sample_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        store.insert(sample_event)
        events = store.get_session_events("sess_001")
        assert len(events) == 1
        assert events[0].action == "page_view"

    def test_insert_multiple_events(self, tmp_path, sample_event, cart_event, checkout_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        store.insert(sample_event)
        store.insert(cart_event)
        store.insert(checkout_event)
        events = store.get_session_events("sess_001")
        assert len(events) == 3
        assert events[1].action == "add_to_cart"

    def test_empty_session(self, tmp_path):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        events = store.get_session_events("nonexistent")
        assert events == []

    def test_event_idempotency(self, tmp_path, sample_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        store.insert(sample_event)
        store.insert(sample_event)  # Same event_id
        events = store.get_session_events("sess_001")
        assert len(events) == 1  # OR REPLACE

    def test_event_ordering(self, tmp_path, sample_event, cart_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        store.insert(cart_event)
        store.insert(sample_event)  # Earlier timestamp
        events = store.get_session_events("sess_001")
        assert events[0].action == "page_view"
        assert events[1].action == "add_to_cart"

    def test_metadata_storage(self, tmp_path):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        event = ClickEvent(
            session_id="sess_002",
            action="search_query",
            metadata={"query": "laptop deals"},
        )
        store.insert(event)
        events = store.get_session_events("sess_002")
        assert events[0].metadata == {"query": "laptop deals"}

    def test_null_value_handling(self, tmp_path):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        event = ClickEvent(
            session_id="sess_003",
            action="page_view",
            product_id=None,
            category=None,
            value=None,
        )
        store.insert(event)
        events = store.get_session_events("sess_003")
        assert events[0].value is None

    def test_large_batch(self, tmp_path):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        for i in range(100):
            event = ClickEvent(session_id="sess_batch", action="page_view", product_id=f"prod_{i}")
            store.insert(event)
        events = store.get_session_events("sess_batch")
        assert len(events) == 100

    def test_multiple_sessions_isolation(self, tmp_path, sample_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        event_a = sample_event.model_copy(update={"session_id": "sess_A", "event_id": "evt_A"})
        event_b = sample_event.model_copy(update={"session_id": "sess_B", "event_id": "evt_B"})
        store.insert(event_a)
        store.insert(event_b)
        assert len(store.get_session_events("sess_A")) == 1
        assert len(store.get_session_events("sess_B")) == 1

    def test_datetime_roundtrip(self, tmp_path, sample_event):
        db = tmp_path / "test.db"
        store = EventStore(db_path=str(db))
        store.insert(sample_event)
        events = store.get_session_events("sess_001")
        assert isinstance(events[0].timestamp, datetime)
