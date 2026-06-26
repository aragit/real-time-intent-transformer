from src.execution.dispatcher import ActionDispatcher
from src.models.features import SessionFeatures


class TestActionDispatcher:
    def test_browse_to_recommend(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        result = d.dispatch("s1", "BROWSE", 0.8, features, True, "")
        assert result.action == "RECOMMEND_ALTERNATIVE"

    def test_checkout_to_urgency(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1", checkouts=1)
        result = d.dispatch("s1", "CHECKOUT_INTENT", 0.9, features, True, "")
        assert result.action == "SHOW_URGENCY"

    def test_governance_deny(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        result = d.dispatch("s1", "CART_BUILDER", 0.8, features, False, "MAX_DISCOUNT_CAP")
        assert result.action == "NO_ACTION"
        assert result.reason == "MAX_DISCOUNT_CAP"

    def test_suppression_cooldown(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        d.dispatch("s1", "BROWSE", 0.8, features, True, "")
        result = d.dispatch("s1", "BROWSE", 0.8, features, True, "")
        assert result.action == "NO_ACTION"
        assert result.reason == "SUPPRESSED_WITHIN_15MIN"

    def test_low_cart_value_blocks_discount(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1", total_cart_value=30)
        result = d.dispatch("s1", "CART_BUILDER", 0.8, features, True, "")
        assert result.action == "NO_ACTION"

    def test_no_checkout_blocks_urgency(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1", checkouts=0)
        result = d.dispatch("s1", "CHECKOUT_INTENT", 0.9, features, True, "")
        assert result.action == "NO_ACTION"

    def test_loyal_returner_reward(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        result = d.dispatch("s1", "LOYAL_RETURNER", 0.9, features, True, "")
        assert result.action == "LOYALTY_REWARD"

    def test_churn_risk_email(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        result = d.dispatch("s1", "CHURN_RISK", 0.7, features, True, "")
        assert result.action == "SEND_ABANDON_EMAIL"

    def test_price_sensitive_discount(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1", total_cart_value=100)
        result = d.dispatch("s1", "PRICE_SENSITIVE", 0.8, features, True, "")
        assert result.action == "APPLY_DISCOUNT"

    def test_unknown_intent_no_action(self):
        d = ActionDispatcher()
        features = SessionFeatures(session_id="s1")
        result = d.dispatch("s1", "UNKNOWN", 0.5, features, True, "")
        assert result.action == "NO_ACTION"
