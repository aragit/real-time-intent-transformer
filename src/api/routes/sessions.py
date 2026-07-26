from fastapi import APIRouter, HTTPException

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


@router.get("/sessions/{session_id}/intent", response_model=IntentPrediction)
async def get_intent(session_id: str):
    """Get current intent prediction + confidence for a session."""
    event_store = get_event_store()
    events = await event_store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    features = _engineer.engineer(events)
    intent, confidence, method = _classifier.classify(features)
    current_state, next_state = _markov.get_chain_prediction(features.action_sequence)
    return IntentPrediction(
        session_id=session_id,
        intent=intent,
        confidence=confidence,
        method=method,
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
