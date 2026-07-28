from fastapi import APIRouter, HTTPException

from langfuse.decorators import observe
from src.memory import get_event_store
from src.models.features import SessionFeatures
from src.models.intent import IntentPrediction
from src.perception.feature_engineer import FeatureEngineer
from src.reasoning.markov_model import MarkovIntentModel

router = APIRouter()
_engineer = FeatureEngineer()
_markov = MarkovIntentModel()


@router.get("/sessions/{session_id}/features", response_model=SessionFeatures)
async def get_features(session_id: str):
    """Get engineered feature vector for a session."""
    event_store = get_event_store()
    events = await event_store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    return _engineer.engineer(events)


@observe(as_type="generation")
@router.get("/sessions/{session_id}/intent", response_model=IntentPrediction)
async def get_intent(session_id: str):
    """Get current intent prediction + confidence for a session via orchestrator."""
    from src.agents.orchestrator import invoke_orchestrator

    event_store = get_event_store()
    events = await event_store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    features = _engineer.engineer(events)

    state = {
        "session_id": session_id,
        "customer_id": events[0].customer_id if events else None,
        "event_type": events[-1].action if events else "page_view",
        "intent": None,
        "confidence": None,
        "recent_events": [e.model_dump(mode="json") for e in events[-20:]],
        "features": features.model_dump(),
        "system": None,
        "result": None,
        "proposed_action": None,
        "opa_evaluation": None,
        "final_action": None,
    }

    result_state = await invoke_orchestrator(state)
    result = result_state.get("result") or {}

    current_state, next_state = _markov.get_chain_prediction(features.action_sequence)
    return IntentPrediction(
        session_id=session_id,
        intent=result.get("intent", "UNKNOWN"),
        confidence=result.get("confidence", 0.0),
        method=result.get("source", "orchestrator"),
        features=features,
        predicted_next_state=next_state,
    )


@router.get("/sessions/{session_id}/markov")
async def get_markov(session_id: str):
    """Get Markov chain current + predicted next state."""
    event_store = get_event_store()
    events = await event_store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    features = _engineer.engineer(events)
    current, next_state = _markov.get_chain_prediction(features.action_sequence)
    return {
        "session_id": session_id,
        "current_state": current,
        "predicted_next_state": next_state,
        "action_history": features.action_sequence,
    }
