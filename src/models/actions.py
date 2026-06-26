from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class ActionDispatch(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str
    intent: str
    confidence: float
    action: str  # APPLY_DISCOUNT, SHOW_URGENCY, SEND_ABANDON_EMAIL, RECOMMEND_ALTERNATIVE, LOYALTY_REWARD, NO_ACTION
    reason: Optional[str] = None
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False
    outcome: Optional[str] = None  # clicked, converted, ignored (stub)
