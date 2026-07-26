from fastapi import APIRouter

from src.execution import get_action_ledger
from src.models.actions import ActionDispatch
from src.pipeline import process_event
from src.models.events import ClickEvent

router = APIRouter()


@router.post("/actions/dispatch", response_model=ActionDispatch)
async def dispatch_action(session_id: str, intent: str, confidence: float):
    """Trigger action dispatch for a session via the async pipeline."""
    event = ClickEvent(
        session_id=session_id,
        action="page_view",
    )
    dispatch = await process_event(event)
    return dispatch


@router.get("/actions/{session_id}/history")
async def get_action_history(session_id: str):
    """Get action ledger for a session."""
    ledger = get_action_ledger()
    return await ledger.get_history(session_id)
