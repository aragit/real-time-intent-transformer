from typing import Dict, Any


class BusinessRules:
    """
    Python fallback for governance when OPA is unavailable.
    Mirrors policies/ecommerce.rego logic.
    """

    @staticmethod
    def evaluate(action: str, customer: Dict[str, Any], features: Dict[str, Any]) -> tuple[bool, str]:
        """
        Returns (allowed, reason).
        """
        # Anti-gaming: max discounts per month
        if action == "APPLY_DISCOUNT":
            if customer.get("discounts_this_month", 0) >= 3:
                return False, "MAX_DISCOUNT_CAP_REACHED"

            if customer.get("last_discount_within_hours", 999) < 24:
                return False, "ANTI_GAMING_COOLDOWN"

            if features.get("total_cart_value", 0) <= 50:
                return False, "MIN_CART_VALUE_NOT_MET"

            if "purchase_complete" in features.get("action_sequence", []):
                return False, "ALREADY_PURCHASED"

        # Urgency only for low inventory + checkout intent
        if action == "SHOW_URGENCY":
            if features.get("inventory_level", 100) >= 10:
                return False, "INVENTORY_SUFFICIENT"
            if features.get("intent") != "CHECKOUT_INTENT":
                return False, "INTENT_MISMATCH"

        # Abandon email only for stalled carts
        if action == "SEND_ABANDON_EMAIL":
            if features.get("session_duration_sec", 0) <= 300:
                return False, "SESSION_TOO_SHORT"
            if features.get("cart_adds", 0) == 0:
                return False, "NO_CART_ITEMS"
            if features.get("checkouts", 0) > 0:
                return False, "ALREADY_CHECKED_OUT"

        # Fairness guardrail: no demographic-based pricing
        if action == "APPLY_DISCOUNT":
            cust_demo = customer.get("demographic_segment")
            feat_demo = features.get("demographic_segment")
            if cust_demo is not None and feat_demo is not None and cust_demo != feat_demo:
                return False, "DEMOGRAPHIC_MISMATCH"

        return True, ""
