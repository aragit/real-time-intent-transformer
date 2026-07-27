from fastapi import APIRouter

from src.perception.feature_engineer import FeatureEngineer
from src.reasoning.ml_ensemble import MLEnsembleClassifier

router = APIRouter()
_engineer = FeatureEngineer()
_classifier = MLEnsembleClassifier()


@router.get("/intents/distribution")
async def get_intent_distribution():
    """Real-time intent class histogram across all sessions."""
    distribution = {
        "BROWSE": 0,
        "COMPARE": 0,
        "CART_BUILDER": 0,
        "CHECKOUT_INTENT": 0,
        "PRICE_SENSITIVE": 0,
        "CHURN_RISK": 0,
        "LOYAL_RETURNER": 0,
    }
    return {
        "distribution": distribution,
        "total_sessions": 0,
        "note": "Stub: requires session indexing for production",
    }
