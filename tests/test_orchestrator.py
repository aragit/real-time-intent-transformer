"""
Orchestrator Routing Logic Tests
=================================
Verifies that the LangGraph orchestrator correctly routes events to
System 1 (fast path) or System 2 (agentic path) based on confidence
thresholds, intent complexity, and exploration signals.
"""

import pytest
from unittest.mock import patch

from src.agents.orchestrator import (
    OrchestratorState,
    route_by_complexity,
    build_orchestrator_graph,
)


def _make_state(
    confidence: float = 0.85,
    intent: str = "BROWSE",
    exploration_ratio: float = 0.2,
    session_id: str = "test_session",
    **kwargs,
) -> OrchestratorState:
    return {
        "session_id": session_id,
        "customer_id": "cust_001",
        "event_type": "page_view",
        "intent": intent,
        "confidence": confidence,
        "recent_events": [],
        "features": {"exploration_ratio": exploration_ratio},
        "system": None,
        "result": None,
        **kwargs,
    }


class TestRoutingLogic:

    def test_high_confidence_routes_to_system_1(self):
        state = _make_state(confidence=0.85)
        assert route_by_complexity(state) == "system_1"

    def test_low_confidence_routes_to_system_2(self):
        state = _make_state(confidence=0.60)
        assert route_by_complexity(state) == "system_2"

    def test_exact_threshold_routes_to_system_1(self):
        state = _make_state(confidence=0.70)
        assert route_by_complexity(state) == "system_1"

    def test_just_below_threshold_routes_to_system_2(self):
        state = _make_state(confidence=0.699)
        assert route_by_complexity(state) == "system_2"

    def test_above_threshold_routes_to_system_1(self):
        state = _make_state(confidence=0.71)
        assert route_by_complexity(state) == "system_1"

    def test_churn_risk_routes_to_system_2(self):
        state = _make_state(confidence=0.90, intent="CHURN_RISK")
        assert route_by_complexity(state) == "system_2"

    def test_loyal_returner_routes_to_system_2(self):
        state = _make_state(confidence=0.90, intent="LOYAL_RETURNER")
        assert route_by_complexity(state) == "system_2"

    def test_high_exploration_routes_to_system_2(self):
        state = _make_state(confidence=0.85, exploration_ratio=0.7)
        assert route_by_complexity(state) == "system_2"

    def test_low_exploration_stays_system_1(self):
        state = _make_state(confidence=0.85, exploration_ratio=0.3)
        assert route_by_complexity(state) == "system_1"

    def test_no_confidence_routes_to_system_1(self):
        state = _make_state(confidence=None)
        assert route_by_complexity(state) == "system_1"

    def test_custom_threshold(self):
        state = _make_state(confidence=0.65)
        with patch("src.agents.orchestrator.settings") as mock_settings:
            mock_settings.system_2_confidence_threshold = 0.60
            assert route_by_complexity(state) == "system_1"

    def test_custom_threshold_below(self):
        state = _make_state(confidence=0.55)
        with patch("src.agents.orchestrator.settings") as mock_settings:
            mock_settings.system_2_confidence_threshold = 0.60
            assert route_by_complexity(state) == "system_2"

    def test_combined_low_confidence_and_churn(self):
        state = _make_state(confidence=0.50, intent="CHURN_RISK")
        assert route_by_complexity(state) == "system_2"

    def test_browse_intent_high_confidence(self):
        state = _make_state(confidence=0.95, intent="BROWSE")
        assert route_by_complexity(state) == "system_1"

    def test_compare_intent_low_confidence(self):
        state = _make_state(confidence=0.40, intent="COMPARE")
        assert route_by_complexity(state) == "system_2"


class TestGraphBuild:

    def test_graph_builds_successfully(self):
        graph = build_orchestrator_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        graph = build_orchestrator_graph()
        # Compiled graph should be invocable
        assert hasattr(graph, "invoke") or hasattr(graph, "ainvoke")
