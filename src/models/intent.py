from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field

from src.models.features import SessionFeatures


class IntentPrediction(BaseModel):
    session_id: str
    intent: str  # BROWSE, COMPARE, CART_BUILDER, CHECKOUT_INTENT, PRICE_SENSITIVE, CHURN_RISK, LOYAL_RETURNER
    confidence: float
    method: str  # rule_based, ml_ensemble, markov_chain
    features: SessionFeatures
    predicted_next_state: Optional[str] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
