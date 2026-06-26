from src.governance.business_rules import BusinessRules


class TestBusinessRules:
    def test_discount_allowed(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {"discounts_this_month": 1}, {"total_cart_value": 100})
        assert allowed is True
        assert reason == ""

    def test_discount_cap_reached(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {"discounts_this_month": 3}, {"total_cart_value": 100})
        assert allowed is False
        assert reason == "MAX_DISCOUNT_CAP_REACHED"

    def test_anti_gaming_cooldown(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {"last_discount_within_hours": 12}, {"total_cart_value": 100})
        assert allowed is False
        assert reason == "ANTI_GAMING_COOLDOWN"

    def test_min_cart_value_not_met(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {}, {"total_cart_value": 30})
        assert allowed is False
        assert reason == "MIN_CART_VALUE_NOT_MET"

    def test_urgency_allowed(self):
        r = BusinessRules()
        allowed, _ = r.evaluate("SHOW_URGENCY", {}, {"inventory_level": 5, "intent": "CHECKOUT_INTENT"})
        assert allowed is True

    def test_urgency_inventory_sufficient(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("SHOW_URGENCY", {}, {"inventory_level": 20, "intent": "CHECKOUT_INTENT"})
        assert allowed is False
        assert reason == "INVENTORY_SUFFICIENT"

    def test_abandon_email_allowed(self):
        r = BusinessRules()
        allowed, _ = r.evaluate("SEND_ABANDON_EMAIL", {}, {"session_duration_sec": 400, "cart_adds": 2, "checkouts": 0})
        assert allowed is True

    def test_abandon_session_too_short(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("SEND_ABANDON_EMAIL", {}, {"session_duration_sec": 100, "cart_adds": 2, "checkouts": 0})
        assert allowed is False
        assert reason == "SESSION_TOO_SHORT"

    def test_already_purchased_blocks_discount(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {}, {"total_cart_value": 100, "action_sequence": ["purchase_complete"]})
        assert allowed is False
        assert reason == "ALREADY_PURCHASED"

    def test_demographic_fairness(self):
        r = BusinessRules()
        allowed, reason = r.evaluate("APPLY_DISCOUNT", {"demographic_segment": "A"}, {"total_cart_value": 100, "demographic_segment": "B"})
        assert allowed is False
        assert reason == "DEMOGRAPHIC_MISMATCH"
