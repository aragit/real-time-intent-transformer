from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import uuid


class ClickEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    session_id: str
    customer_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action: str  # page_view, add_to_cart, remove_from_cart, checkout_start, purchase_complete, search_query, filter_apply
    product_id: Optional[str] = None
    category: Optional[str] = None
    value: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
