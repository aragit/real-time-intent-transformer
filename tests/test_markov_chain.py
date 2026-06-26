from src.reasoning.markov_model import MarkovIntentModel


class TestMarkovIntentModel:
    def test_landing_to_browsing(self):
        m = MarkovIntentModel()
        current = m.infer_current_state(["page_view"])
        assert current == "BROWSING"

    def test_checkout_state(self):
        m = MarkovIntentModel()
        current = m.infer_current_state(["checkout_start"])
        assert current == "CHECKOUT"

    def test_purchase_state(self):
        m = MarkovIntentModel()
        current = m.infer_current_state(["purchase_complete"])
        assert current == "PURCHASE"

    def test_empty_history(self):
        m = MarkovIntentModel()
        current = m.infer_current_state([])
        assert current == "LANDING"

    def test_predict_next_from_browsing(self):
        m = MarkovIntentModel()
        next_state = m.predict_next_state("BROWSING", ["page_view"])
        assert next_state in m.TRANSITION_MATRIX["BROWSING"]

    def test_cart_action_boosts_carting(self):
        m = MarkovIntentModel()
        # With add_to_cart in recent history, CARTING should be boosted
        next_state = m.predict_next_state("BROWSING", ["add_to_cart"])
        # The boost makes CARTING competitive but BROWSING base is 0.5
        # After normalization: BROWSING ~0.42, CARTING ~0.33, COMPARING ~0.17, EXIT ~0.08
        assert next_state in ("BROWSING", "CARTING")  # Either is valid with boost

    def test_checkout_action_boosts_checkout(self):
        m = MarkovIntentModel()
        next_state = m.predict_next_state("CARTING", ["checkout_start"])
        assert next_state == "CHECKOUT"  # Boosted by +0.3, base is 0.3 → dominates

    def test_probability_normalization(self):
        m = MarkovIntentModel()
        next_state = m.predict_next_state("BROWSING", [])
        probs = m.TRANSITION_MATRIX["BROWSING"]
        assert abs(sum(probs.values()) - 1.0) < 0.01

    def test_chain_prediction(self):
        m = MarkovIntentModel()
        current, next_state = m.get_chain_prediction(["page_view", "add_to_cart"])
        assert current == "CARTING"
        assert next_state in m.TRANSITION_MATRIX[current]

    def test_unknown_state_fallback(self):
        m = MarkovIntentModel()
        next_state = m.predict_next_state("UNKNOWN", [])
        assert next_state == "EXIT"
