"""
Orchestrator Routing Logic Tests
================================
Verifies that the LangGraph orchestrator correctly routes events to
System 1 (fast path) or System 2 (agentic path) based on confidence
thresholds, intent complexity, and exploration signals.

Also verifies the full graph execution flow including the Critic Agent.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.orchestrator import (
    OrchestratorState,
    build_orchestrator_graph,
    route_by_complexity,
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
        "proposed_action": None,
        "opa_evaluation": None,
        "final_action": None,
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


# ---------------------------------------------------------------------------
# Full graph execution tests (System 2 → Critic → END)
# ---------------------------------------------------------------------------


class TestGraphExecution:
    @pytest.mark.asyncio
    async def test_system_2_flows_through_critic(self):
        """Verify the full state transition: route → system_2 → critic → END."""
        mock_planner_result = {
            "action": "APPLY_DISCOUNT",
            "confidence": 0.45,
            "reasoning": "Low confidence session needs intervention",
            "product_context": "Electronics",
            "customer_segment": "price_sensitive",
            "source": "system_2_planner",
        }

        mock_critic_result = {
            "action": "FREE_SHIPPING",
            "reasoning": "Critic rewrite: discount exceeds policy cap",
            "source": "system_2_critic_rewrite",
            "opa_allowed": False,
        }

        with (
            patch("src.agents.planner.run_planner", new_callable=AsyncMock) as mock_planner,
            patch("src.agents.critic.run_critic", new_callable=AsyncMock) as mock_critic,
            patch("src.agents.orchestrator.settings") as mock_settings,
        ):
            mock_settings.system_2_confidence_threshold = 0.70
            mock_planner.return_value = mock_planner_result
            mock_critic.return_value = mock_critic_result

            graph = build_orchestrator_graph()
            initial_state = _make_state(
                confidence=0.45,
                intent="PRICE_SENSITIVE",
            )

            final_state = await graph.ainvoke(
                initial_state, config={"configurable": {"thread_id": "test"}}
            )

        # Verify state transitions
        assert final_state["system"] == "system_2"
        assert final_state["proposed_action"] == "APPLY_DISCOUNT"
        assert final_state["opa_evaluation"]["allowed"] is False
        assert final_state["opa_evaluation"]["proposed_action"] == "APPLY_DISCOUNT"
        assert final_state["final_action"]["action"] == "FREE_SHIPPING"
        assert final_state["final_action"]["source"] == "system_2_critic_rewrite"
        assert final_state["result"]["action"] == "FREE_SHIPPING"

    @pytest.mark.asyncio
    async def test_system_2_opa_approved_flow(self):
        """Verify System 2 path when OPA approves the Planner's action."""
        mock_planner_result = {
            "action": "SHOW_URGENCY",
            "confidence": 0.60,
            "reasoning": "Low stock detected on viewed product",
            "product_context": "Limited edition sneakers",
            "customer_segment": "impulse_buyer",
            "source": "system_2_planner",
        }

        mock_critic_result = {
            "action": "SHOW_URGENCY",
            "reasoning": "Low stock urgency is policy-compliant",
            "source": "system_2_critic_approved",
            "opa_allowed": True,
        }

        with (
            patch("src.agents.planner.run_planner", new_callable=AsyncMock) as mock_planner,
            patch("src.agents.critic.run_critic", new_callable=AsyncMock) as mock_critic,
            patch("src.agents.orchestrator.settings") as mock_settings,
        ):
            mock_settings.system_2_confidence_threshold = 0.70
            mock_planner.return_value = mock_planner_result
            mock_critic.return_value = mock_critic_result

            graph = build_orchestrator_graph()
            initial_state = _make_state(
                confidence=0.55,
                intent="BROWSE",
            )

            final_state = await graph.ainvoke(
                initial_state, config={"configurable": {"thread_id": "test"}}
            )

        assert final_state["proposed_action"] == "SHOW_URGENCY"
        assert final_state["opa_evaluation"]["allowed"] is True
        assert final_state["final_action"]["action"] == "SHOW_URGENCY"
        assert final_state["final_action"]["source"] == "system_2_critic_approved"

    @pytest.mark.asyncio
    async def test_system_2_hard_rejection_flow(self):
        """Verify System 2 path when both OPA and LLM fail → NO_ACTION."""
        mock_planner_result = {
            "action": "OFFER_DISCOUNT",
            "confidence": 0.40,
            "reasoning": "Churning customer needs incentive",
            "product_context": "",
            "customer_segment": "churning",
            "source": "system_2_planner",
        }

        mock_critic_result = {
            "action": "NO_ACTION",
            "reasoning": "OPA denied 'OFFER_DISCOUNT': policy violation",
            "source": "system_2_critic_rejected",
            "opa_allowed": False,
        }

        with (
            patch("src.agents.planner.run_planner", new_callable=AsyncMock) as mock_planner,
            patch("src.agents.critic.run_critic", new_callable=AsyncMock) as mock_critic,
            patch("src.agents.orchestrator.settings") as mock_settings,
        ):
            mock_settings.system_2_confidence_threshold = 0.70
            mock_planner.return_value = mock_planner_result
            mock_critic.return_value = mock_critic_result

            graph = build_orchestrator_graph()
            initial_state = _make_state(
                confidence=0.35,
                intent="CHURN_RISK",
            )

            final_state = await graph.ainvoke(
                initial_state, config={"configurable": {"thread_id": "test"}}
            )

        assert final_state["proposed_action"] == "OFFER_DISCOUNT"
        assert final_state["opa_evaluation"]["allowed"] is False
        assert final_state["final_action"]["action"] == "NO_ACTION"
        assert final_state["final_action"]["source"] == "system_2_critic_rejected"

    @pytest.mark.asyncio
    async def test_system_1_bypasses_critic(self):
        """Verify System 1 path does NOT invoke the Critic Agent."""
        mock_dispatch = MagicMock()
        mock_dispatch.action = "SHOW_URGENCY"
        mock_dispatch.intent = "CHECKOUT_INTENT"
        mock_dispatch.confidence = 0.92
        mock_dispatch.reason = "High confidence"

        with (
            patch("src.pipeline.process_event", new_callable=AsyncMock) as mock_process,
            patch("src.agents.critic.run_critic", new_callable=AsyncMock) as mock_critic,
            patch("src.agents.orchestrator.settings") as mock_settings,
        ):
            mock_settings.system_2_confidence_threshold = 0.70
            mock_process.return_value = mock_dispatch

            graph = build_orchestrator_graph()
            initial_state = _make_state(confidence=0.92, intent="CHECKOUT_INTENT")

            final_state = await graph.ainvoke(
                initial_state, config={"configurable": {"thread_id": "test"}}
            )

        assert final_state["system"] == "system_1"
        assert final_state["result"]["source"] == "system_1"
        mock_critic.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_keys_populated_after_system_2(self):
        """Verify all new state keys are populated after System 2 + Critic."""
        mock_planner_result = {
            "action": "NO_ACTION",
            "confidence": 0.50,
            "reasoning": "Browsing pattern",
            "product_context": "",
            "customer_segment": "unknown",
            "source": "system_2_planner",
        }

        mock_critic_result = {
            "action": "NO_ACTION",
            "reasoning": "Approved as-is",
            "source": "system_2_critic_approved",
            "opa_allowed": True,
        }

        with (
            patch("src.agents.planner.run_planner", new_callable=AsyncMock) as mock_planner,
            patch("src.agents.critic.run_critic", new_callable=AsyncMock) as mock_critic,
            patch("src.agents.orchestrator.settings") as mock_settings,
        ):
            mock_settings.system_2_confidence_threshold = 0.70
            mock_planner.return_value = mock_planner_result
            mock_critic.return_value = mock_critic_result

            graph = build_orchestrator_graph()
            initial_state = _make_state(confidence=0.50)

            final_state = await graph.ainvoke(
                initial_state, config={"configurable": {"thread_id": "test"}}
            )

        # All new keys must be present and non-None
        assert final_state["proposed_action"] is not None
        assert final_state["opa_evaluation"] is not None
        assert final_state["final_action"] is not None

        # Verify structure of opa_evaluation
        assert "allowed" in final_state["opa_evaluation"]
        assert "proposed_action" in final_state["opa_evaluation"]

        # Verify structure of final_action
        assert "action" in final_state["final_action"]
        assert "source" in final_state["final_action"]
        assert "reason" in final_state["final_action"]
