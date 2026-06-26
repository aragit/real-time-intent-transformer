from typing import List

from fastapi import APIRouter, HTTPException, status

from src.ingestion.event_store import EventStore
from src.ingestion.kafka_producer import ClickstreamProducer
from src.models.events import ClickEvent

router = APIRouter()

# Lazy initialization for testability
_producer: ClickstreamProducer | None = None
_store = EventStore()


def _get_producer() -> ClickstreamProducer:
    global _producer
    if _producer is None:
        _producer = ClickstreamProducer()
    return _producer


@router.post("/events/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event(event: ClickEvent):
    """Ingest a single click event."""
    producer = _get_producer()
    await producer.start()
    try:
        await producer.send_event(event)
        _store.insert(event)
    finally:
        await producer.stop()
    return {"status": "accepted", "event_id": event.event_id}


@router.post("/events/ingest/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(events: List[ClickEvent]):
    """Ingest a batch of click events."""
    producer = _get_producer()
    await producer.start()
    try:
        await producer.send_batch(events)
        for event in events:
            _store.insert(event)
    finally:
        await producer.stop()
    return {"status": "accepted", "count": len(events)}
