from fastapi import APIRouter, HTTPException

from langfuse.decorators import observe
from src.memory import get_event_store
from src.models.features import SessionFeatures
from src.models.intent import IntentPrediction
from src.perception.feature_engineer import FeatureEngineer
from src.reasoning.markov_model import MarkovIntentModel
from src.reasoning.ml_ensemble import MLEnsembleClassifier

router = APIRouter()
_engineer = FeatureEngineer()
_classifier = MLEnsembleClassifier()
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
    """Get current intent prediction + confidence for a session via dual-path orchestrator."""
    from src.agents.orchestrator import MAX_STATE_EVENTS, OrchestratorState, invoke_orchestrator

    event_store = get_event_store()
    events = await event_store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")

    features = _engineer.engineer(events)
    intent, confidence, method = _classifier.classify(features)
    current_state, next_state = _markov.get_chain_prediction(features.action_sequence)

    state: OrchestratorState = {
        "session_id": session_id,
        "customer_id": features.customer_id,
        "event_type": events[-1].action if events else "page_view",
        "intent": intent,
        "confidence": confidence,
        "recent_events": [e.model_dump() for e in events[-MAX_STATE_EVENTS:]],
        "features": features.model_dump(),
        "system": None,
        "result": None,
        "proposed_action": None,
        "opa_evaluation": None,
        "final_action": None,
    }

    final_state = await invoke_orchestrator(state)

    result = final_state.get("final_action") or final_state.get("result") or {}

    return IntentPrediction(
        session_id=session_id,
        intent=result.get("intent", intent),
        confidence=result.get("confidence", confidence),
        method=result.get("source", method),
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
