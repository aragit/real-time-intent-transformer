from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field

from src.models.intent import IntentPrediction


class CustomerProfile(BaseModel):
    customer_id: str
    total_sessions: int = 0
    total_purchases: int = 0
    lifetime_value: float = 0.0
    avg_session_duration: float = 0.0
    preferred_categories: List[str] = Field(default_factory=list)
    intent_history: List[IntentPrediction] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
