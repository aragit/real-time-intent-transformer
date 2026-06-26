from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class SessionFeatures(BaseModel):
    session_id: str
    customer_id: Optional[str] = None
    session_duration_sec: float = 0.0
    total_actions: int = 0
    page_views: int = 0
    cart_adds: int = 0
    cart_removes: int = 0
    checkouts: int = 0
    searches: int = 0
    total_cart_value: float = 0.0
    max_item_value: float = 0.0
    avg_item_value: float = 0.0
    categories_viewed: int = 0
    category_switches: int = 0
    cart_conversion_rate: float = 0.0
    checkout_conversion_rate: float = 0.0
    cart_abandon_rate: float = 0.0
    exploration_ratio: float = 0.0
    cart_value_per_minute: float = 0.0
    avg_inter_event_time: float = 0.0
    action_sequence: List[str] = Field(default_factory=list)
    repeat_customer: bool = False
    days_since_last_purchase: Optional[int] = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
