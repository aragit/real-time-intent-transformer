from typing import Tuple

from src.models.features import SessionFeatures


class RuleBasedClassifier:
    """Fast deterministic heuristic scoring. Latency target: <10ms."""

    INTENT_CLASSES = [
        "BROWSE",
        "COMPARE",
        "CART_BUILDER",
        "CHECKOUT_INTENT",
        "PRICE_SENSITIVE",
        "CHURN_RISK",
        "LOYAL_RETURNER",
    ]

    def classify(self, features: SessionFeatures) -> Tuple[str, float]:
        scores = {intent: 0 for intent in self.INTENT_CLASSES}

        # BROWSE: high page views, low cart activity, high exploration
        if features.page_views > 5 and features.cart_adds == 0:
            scores["BROWSE"] += 3
        if features.exploration_ratio > 0.5:
            scores["BROWSE"] += 2

        # COMPARE: multiple categories, repeated views, no cart
        if features.categories_viewed > 3 and features.cart_adds == 0:
            scores["COMPARE"] += 3
        pv_count = features.action_sequence.count("page_view")
        ac_count = features.action_sequence.count("add_to_cart")
        if pv_count > ac_count * 3:
            scores["COMPARE"] += 2

        # CART_BUILDER: cart adds > removes, moderate value
        if features.cart_adds > features.cart_removes and features.total_cart_value > 50:
            scores["CART_BUILDER"] += 3
        if features.cart_conversion_rate > 0.3:
            scores["CART_BUILDER"] += 2

        # CHECKOUT_INTENT: checkout started, high value, low exploration
        if features.checkouts > 0:
            scores["CHECKOUT_INTENT"] += 4
        if features.total_cart_value > 100 and features.exploration_ratio < 0.3:
            scores["CHECKOUT_INTENT"] += 2

        # PRICE_SENSITIVE: high searches, cart removes
        if features.searches > 3:
            scores["PRICE_SENSITIVE"] += 3
        if features.cart_abandon_rate > 0.5:
            scores["PRICE_SENSITIVE"] += 2

        # CHURN_RISK: long session, no cart, high time since last purchase
        if features.session_duration_sec > 600 and features.cart_adds == 0:
            scores["CHURN_RISK"] += 2
        if features.days_since_last_purchase and features.days_since_last_purchase > 30:
            scores["CHURN_RISK"] += 3

        # LOYAL_RETURNER: repeat customer, quick decisions, high value
        if features.repeat_customer:
            scores["LOYAL_RETURNER"] += 3
        if features.avg_inter_event_time < 30 and features.total_cart_value > 100:
            scores["LOYAL_RETURNER"] += 2

        total = sum(scores.values())
        if total == 0:
            return "BROWSE", 0.0

        best = max(scores, key=scores.get)
        confidence = scores[best] / total
        return best, min(confidence, 1.0)
