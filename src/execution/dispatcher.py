from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from loguru import logger

from src.models.actions import ActionDispatch
from src.models.features import SessionFeatures


class ActionDispatcher:
    """Maps intent to action with governance checks."""

    ACTION_MAP = {
        "BROWSE": "RECOMMEND_ALTERNATIVE",
        "COMPARE": "SHOW_COMPARISON_TOOL",
        "CART_BUILDER": "APPLY_DISCOUNT",
        "CHECKOUT_INTENT": "SHOW_URGENCY",
        "PRICE_SENSITIVE": "APPLY_DISCOUNT",
        "CHURN_RISK": "SEND_ABANDON_EMAIL",
        "LOYAL_RETURNER": "LOYALTY_REWARD",
    }

    def __init__(self):
        self._suppression: Dict[str, datetime] = {}

    def dispatch(
        self,
        session_id: str,
        intent: str,
        confidence: float,
        features: SessionFeatures,
        governance_allowed: bool,
        governance_reason: str,
    ) -> ActionDispatch:
        # Suppression: no duplicate action within 15 minutes
        now = datetime.now(timezone.utc)
        last_dispatch = self._suppression.get(session_id)
        if last_dispatch and (now - last_dispatch) < timedelta(minutes=15):
            return ActionDispatch(
                session_id=session_id,
                intent=intent,
                confidence=confidence,
                action="NO_ACTION",
                reason="SUPPRESSED_WITHIN_15MIN",
            )

        # Governance deny
        if not governance_allowed:
            return ActionDispatch(
                session_id=session_id,
                intent=intent,
                confidence=confidence,
                action="NO_ACTION",
                reason=governance_reason,
            )

        action = self.ACTION_MAP.get(intent, "NO_ACTION")

        # Additional business logic
        if action == "APPLY_DISCOUNT" and features.total_cart_value < 50:
            action = "NO_ACTION"
            governance_reason = "MIN_CART_VALUE_NOT_MET"

        if action == "SHOW_URGENCY" and features.checkouts == 0:
            action = "NO_ACTION"
            governance_reason = "NO_CHECKOUT_STARTED"

        if action != "NO_ACTION":
            self._suppression[session_id] = now

        return ActionDispatch(
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            action=action,
            reason=governance_reason if action == "NO_ACTION" else None,
        )
