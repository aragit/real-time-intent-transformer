from typing import List

from fastapi import APIRouter, status

from src.models.events import ClickEvent
from src.pipeline import ingest_event

router = APIRouter()


@router.post("/events/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_event_endpoint(event: ClickEvent):
    """Ingest a single click event into async memory stores."""
    await ingest_event(event)
    return {"status": "accepted", "event_id": event.event_id}


@router.post("/events/ingest/batch", status_code=status.HTTP_202_ACCEPTED)
async def ingest_batch(events: List[ClickEvent]):
    """Ingest a batch of click events into async memory stores."""
    import asyncio
    await asyncio.gather(*[ingest_event(e) for e in events])
    return {"status": "accepted", "count": len(events)}
