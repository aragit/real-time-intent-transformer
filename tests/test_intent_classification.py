from src.models.features import SessionFeatures
from src.reasoning.rule_classifier import RuleBasedClassifier


class TestRuleBasedClassifier:
    def test_browse_high_pageviews_no_cart(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            page_views=8,
            cart_adds=0,
            exploration_ratio=0.6,
        )
        intent, conf = clf.classify(features)
        assert intent == "BROWSE"
        assert conf > 0.5

    def test_compare_multiple_categories(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            categories_viewed=4,
            cart_adds=0,
            action_sequence=["page_view"] * 6,
        )
        intent, conf = clf.classify(features)
        assert intent == "COMPARE"

    def test_cart_builder(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            cart_adds=3,
            cart_removes=1,
            total_cart_value=75,
            cart_conversion_rate=0.5,
        )
        intent, conf = clf.classify(features)
        assert intent == "CART_BUILDER"

    def test_checkout_intent(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            checkouts=1,
            total_cart_value=150,
            exploration_ratio=0.1,
        )
        intent, conf = clf.classify(features)
        assert intent == "CHECKOUT_INTENT"

    def test_price_sensitive(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            searches=4,
            cart_abandon_rate=0.6,
        )
        intent, conf = clf.classify(features)
        assert intent == "PRICE_SENSITIVE"

    def test_churn_risk_long_session_no_cart(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            session_duration_sec=700,
            cart_adds=0,
            days_since_last_purchase=45,
        )
        intent, conf = clf.classify(features)
        assert intent == "CHURN_RISK"

    def test_loyal_returner(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            repeat_customer=True,
            avg_inter_event_time=20,
            total_cart_value=200,
        )
        intent, conf = clf.classify(features)
        assert intent == "LOYAL_RETURNER"

    def test_confidence_bounds(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(session_id="s1")
        _, conf = clf.classify(features)
        assert 0.0 <= conf <= 1.0

    def test_no_negative_scores(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(session_id="s1", page_views=-5)
        intent, conf = clf.classify(features)
        assert intent in clf.INTENT_CLASSES

    def test_ambiguous_fallback(self):
        clf = RuleBasedClassifier()
        features = SessionFeatures(
            session_id="s1",
            page_views=2,
            cart_adds=1,
            checkouts=0,
        )
        intent, conf = clf.classify(features)
        assert intent in clf.INTENT_CLASSES
        assert conf < 0.6  # Low confidence triggers ML fallback in production
