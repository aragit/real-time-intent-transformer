import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ClickEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str
    customer_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action: str  # page_view, add_to_cart, remove_from_cart, checkout_start, purchase_complete, search_query, filter_apply
    product_id: str | None = None
    category: str | None = None
    value: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
