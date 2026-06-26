from fastapi import APIRouter, HTTPException

from src.ingestion.event_store import EventStore
from src.models.features import SessionFeatures
from src.models.intent import IntentPrediction
from src.perception.feature_engineer import FeatureEngineer
from src.reasoning.markov_model import MarkovIntentModel
from src.reasoning.ml_ensemble import MLEnsembleClassifier

router = APIRouter()
store = EventStore()
engineer = FeatureEngineer()
classifier = MLEnsembleClassifier()
markov = MarkovIntentModel()


@router.get("/sessions/{session_id}/features", response_model=SessionFeatures)
async def get_features(session_id: str):
    """Get engineered feature vector for a session."""
    events = store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    return engineer.engineer(events)


@router.get("/sessions/{session_id}/intent", response_model=IntentPrediction)
async def get_intent(session_id: str):
    """Get current intent prediction + confidence for a session."""
    events = store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    features = engineer.engineer(events)
    intent, confidence, method = classifier.classify(features)
    current_state, next_state = markov.get_chain_prediction(features.action_sequence)
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
    events = store.get_session_events(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Session not found")
    features = engineer.engineer(events)
    current, next_state = markov.get_chain_prediction(features.action_sequence)
    return {
        "session_id": session_id,
        "current_state": current,
        "predicted_next_state": next_state,
        "action_history": features.action_sequence,
    }
