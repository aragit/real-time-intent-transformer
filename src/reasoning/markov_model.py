from typing import Dict, List, Optional

import numpy as np


class MarkovIntentModel:
    """
    Models intent as state transitions.
    States: LANDING → BROWSING → COMPARING → CARTING → CHECKOUT → PURCHASE → EXIT
    """

    TRANSITION_MATRIX: Dict[str, Dict[str, float]] = {
        "LANDING": {"BROWSING": 0.7, "EXIT": 0.3},
        "BROWSING": {"BROWSING": 0.5, "COMPARING": 0.2, "CARTING": 0.1, "EXIT": 0.2},
        "COMPARING": {"COMPARING": 0.4, "CARTING": 0.3, "BROWSING": 0.2, "EXIT": 0.1},
        "CARTING": {"CARTING": 0.4, "CHECKOUT": 0.3, "BROWSING": 0.2, "EXIT": 0.1},
        "CHECKOUT": {"PURCHASE": 0.6, "CARTING": 0.2, "EXIT": 0.2},
        "PURCHASE": {"EXIT": 0.8, "BROWSING": 0.2},
    }

    ACTION_TO_STATE = {
        "page_view": "BROWSING",
        "search_query": "COMPARING",
        "add_to_cart": "CARTING",
        "remove_from_cart": "BROWSING",
        "checkout_start": "CHECKOUT",
        "purchase_complete": "PURCHASE",
    }

    def infer_current_state(self, action_history: List[str]) -> str:
        """Infer most likely current state from action history."""
        if not action_history:
            return "LANDING"
        last_action = action_history[-1]
        return self.ACTION_TO_STATE.get(last_action, "BROWSING")

    def predict_next_state(self, current_state: str, action_history: List[str]) -> str:
        """Predict most likely next state with action-weighted adjustments."""
        if current_state not in self.TRANSITION_MATRIX:
            return "EXIT"

        adjusted = self.TRANSITION_MATRIX[current_state].copy()

        # Weight recent actions
        if action_history:
            weights = np.exp(np.linspace(-1, 0, len(action_history)))
            for action, w in zip(action_history, weights):
                if w > 0.3:
                    if action == "add_to_cart":
                        adjusted["CARTING"] = adjusted.get("CARTING", 0) + 0.2
                    elif action == "checkout_start":
                        adjusted["CHECKOUT"] = adjusted.get("CHECKOUT", 0) + 0.3
                    elif action == "search_query":
                        adjusted["COMPARING"] = adjusted.get("COMPARING", 0) + 0.1

        # Normalize
        total = sum(adjusted.values())
        adjusted = {k: v / total for k, v in adjusted.items()}

        return max(adjusted, key=adjusted.get)

    def get_chain_prediction(self, action_history: List[str]) -> tuple[str, str]:
        """Return (current_state, predicted_next_state)."""
        current = self.infer_current_state(action_history)
        next_state = self.predict_next_state(current, action_history)
        return current, next_state
