from fastapi import APIRouter, HTTPException

from src.execution.dispatcher import ActionDispatcher
from src.execution.ledger import ActionLedger
from src.governance.business_rules import BusinessRules
from src.models.actions import ActionDispatch
from src.models.features import SessionFeatures

router = APIRouter()
dispatcher = ActionDispatcher()
ledger = ActionLedger()
rules = BusinessRules()


@router.post("/actions/dispatch", response_model=ActionDispatch)
async def dispatch_action(session_id: str, intent: str, confidence: float):
    """Trigger action dispatch for a session."""
    # In real flow, features would come from session store
    # Here we accept minimal params for API contract
    features = SessionFeatures(session_id=session_id)  # Placeholder
    customer = {}  # Placeholder

    allowed, reason = rules.evaluate(intent, customer, features.model_dump())
    dispatch = dispatcher.dispatch(session_id, intent, confidence, features, allowed, reason)
    ledger.record(dispatch)
    return dispatch


@router.get("/actions/{session_id}/history")
async def get_action_history(session_id: str):
    """Get action ledger for a session."""
    return ledger.get_history(session_id)
