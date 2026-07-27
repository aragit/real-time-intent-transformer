import hashlib
from datetime import UTC, datetime

from pydantic import BaseModel, Field


def _deterministic_action_id(session_id: str, action: str, timestamp: datetime) -> str:
    """Generate a deterministic idempotency key from session, action, and minute-bucket.

    This ensures that graph retries or re-dispatches within the same minute
    produce the same action_id, allowing PostgreSQL ON CONFLICT to deduplicate.
    """
    minute_bucket = int(timestamp.timestamp()) // 60
    raw = f"{session_id}:{action}:{minute_bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


class ActionDispatch(BaseModel):
    action_id: str = ""
    session_id: str
    intent: str
    confidence: float
    action: str
    reason: str | None = None
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    acknowledged: bool = False
    outcome: str | None = None

    def model_post_init(self, __context) -> None:
        if not self.action_id:
            self.action_id = _deterministic_action_id(
                self.session_id, self.action, self.dispatched_at
            )
