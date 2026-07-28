"""
Planner Agent Tests
====================
Tests for the System 2 Planner Agent with mocked LLM and tool execution.

Verifies that:
- The planner correctly parses structured JSON from LLM output
- The planner falls back gracefully on malformed output
- The planner handles LLM errors without crashing
- The input builder formats session data correctly
- Tool invocations are properly routed
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.planner import (
    PLANNER_SYSTEM_PROMPT,
    PLANNER_TOOLS,
    build_planner_input,
    run_planner,
)

# ---------------------------------------------------------------------------
# build_planner_input tests
# ---------------------------------------------------------------------------


class TestBuildPlannerInput:
    def test_formats_session_data(self):
        result = build_planner_input(
            session_id="sess_001",
            customer_id="cust_001",
            intent="BROWSE",
            confidence=0.65,
            recent_events=[
                {
                    "action": "page_view",
                    "product_id": "prod_1",
                    "category": "electronics",
                    "value": 99.99,
                },
                {
                    "action": "add_to_cart",
                    "product_id": "prod_2",
                    "category": "electronics",
                    "value": 149.99,
                },
            ],
            features={
                "session_duration_sec": 120,
                "total_actions": 5,
                "total_cart_value": 249.98,
                "cart_adds": 2,
                "checkouts": 0,
                "category_switches": 1,
                "exploration_ratio": 0.33,
            },
        )

        assert "sess_001" in result
        assert "cust_001" in result
        assert "BROWSE" in result
        assert "0.65" in result
        assert "page_view" in result
        assert "add_to_cart" in result
        assert "query_product_graph" in result
        assert "get_customer_affinity" in result

    def test_anonymous_customer(self):
        result = build_planner_input(
            session_id="sess_002",
            customer_id=None,
            intent="COMPARE",
            confidence=0.45,
            recent_events=[],
            features={"session_duration_sec": 30, "total_actions": 2},
        )

        assert "anonymous" in result
        assert "No recent events" in result
        assert "get_customer_affinity" not in result

    def test_limits_events_to_10(self):
        events = [
            {
                "action": f"action_{i}",
                "product_id": f"prod_{i}",
                "category": "misc",
                "value": float(i),
            }
            for i in range(20)
        ]
        result = build_planner_input(
            session_id="sess_003",
            customer_id="cust_003",
            intent="BROWSE",
            confidence=0.80,
            recent_events=events,
            features={},
        )

        assert "action_0" not in result
        assert "action_19" in result
        assert "action_10" in result


# ---------------------------------------------------------------------------
# Planner tool list tests
# ---------------------------------------------------------------------------


class TestPlannerTools:
    def test_has_two_tools(self):
        assert len(PLANNER_TOOLS) == 2

    def test_tools_are_named(self):
        names = [t.name for t in PLANNER_TOOLS]
        assert "query_product_graph" in names
        assert "get_customer_affinity" in names


# ---------------------------------------------------------------------------
# System prompt tests
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    def test_contains_action_options(self):
        actions = [
            "OFFER_BUNDLE",
            "SEND_ABANDON_EMAIL",
            "OFFER_DISCOUNT",
            "SEND_TO_HUMAN",
            "NO_ACTION",
            "SHOW_URGENCY",
        ]
        for action in actions:
            assert action in PLANNER_SYSTEM_PROMPT

    def test_contains_response_format(self):
        assert "JSON" in PLANNER_SYSTEM_PROMPT
        assert "action" in PLANNER_SYSTEM_PROMPT
        assert "confidence" in PLANNER_SYSTEM_PROMPT
        assert "reasoning" in PLANNER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# run_planner tests (mocked LLM)
# ---------------------------------------------------------------------------


def _make_mock_llm(output: str) -> MagicMock:
    """Create a mock LLM that returns the given output (no tool calls)."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = output
    mock_response.tool_calls = []
    mock_llm.bind_tools.return_value = mock_llm
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


class TestRunPlanner:
    @pytest.mark.asyncio
    async def test_successful_json_parse(self):
        mock_output = json.dumps(
            {
                "action": "OFFER_BUNDLE",
                "confidence": 0.85,
                "reasoning": "Customer showing high cart interest with category switching",
                "product_context": "MacBook Pro, USB-C Hub",
                "customer_segment": "tech_enthusiast",
            }
        )

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_json",
                customer_id="cust_001",
                intent="BROWSE",
                confidence=0.55,
                recent_events=[],
                features={},
            )

        assert result["action"] == "OFFER_BUNDLE"
        assert result["confidence"] == 0.85
        assert result["source"] == "system_2_planner"
        assert "tech_enthusiast" in result["customer_segment"]

    @pytest.mark.asyncio
    async def test_json_in_markdown_block(self):
        mock_output = f"""Here's my analysis:

```json
{
            json.dumps(
                {
                    "action": "SHOW_URGENCY",
                    "confidence": 0.72,
                    "reasoning": "Low stock detected",
                    "product_context": "Limited edition item",
                    "customer_segment": "impulse_buyer",
                }
            )
        }
```

I recommend creating urgency."""

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_md",
                customer_id="cust_002",
                intent="PRICE_SENSITIVE",
                confidence=0.60,
                recent_events=[],
                features={},
            )

        assert result["action"] == "SHOW_URGENCY"
        assert result["confidence"] == 0.72

    @pytest.mark.asyncio
    async def test_plain_text_fallback_bundle(self):
        mock_output = "Based on the analysis, I recommend OFFER_BUNDLE to this customer."

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_fallback",
                customer_id="cust_003",
                intent="COMPARE",
                confidence=0.50,
                recent_events=[],
                features={},
            )

        assert result["action"] == "OFFER_BUNDLE"
        assert result["source"] == "system_2_planner"

    @pytest.mark.asyncio
    async def test_plain_text_fallback_no_action(self):
        mock_output = "The customer seems to be browsing normally. No intervention needed."

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_noaction",
                customer_id="cust_004",
                intent="BROWSE",
                confidence=0.75,
                recent_events=[],
                features={},
            )

        assert result["action"] == "NO_ACTION"

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_error(self):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(side_effect=TimeoutError("LLM request timed out"))

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_timeout",
                customer_id="cust_005",
                intent="BROWSE",
                confidence=0.60,
                recent_events=[],
                features={},
            )

        assert result["action"] == "NO_ACTION"
        assert result["confidence"] == 0.0
        assert result["source"] == "system_2_error"
        assert "timed out" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_llm_connection_error_returns_error(self):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.ainvoke = AsyncMock(side_effect=ConnectionError("Cannot reach Ollama server"))

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_conn_err",
                customer_id="cust_006",
                intent="BROWSE",
                confidence=0.60,
                recent_events=[],
                features={},
            )

        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_error"
        assert "Cannot reach" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_empty_output_returns_no_action(self):
        mock_llm = _make_mock_llm("")

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_empty",
                customer_id=None,
                intent="BROWSE",
                confidence=0.65,
                recent_events=[],
                features={},
            )

        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_planner"

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_text(self):
        mock_output = '{"action": "OFFER_BUNDLE" incomplete json...'

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_malformed",
                customer_id="cust_007",
                intent="BROWSE",
                confidence=0.60,
                recent_events=[],
                features={},
            )

        assert result["action"] == "OFFER_BUNDLE"
        assert result["source"] == "system_2_planner"

    @pytest.mark.asyncio
    async def test_send_to_human_detected(self):
        mock_output = "This case is too complex. I recommend SEND_TO_HUMAN for manual review."

        mock_llm = _make_mock_llm(mock_output)

        with patch("src.agents.planner._get_llm", return_value=mock_llm):
            result = await run_planner(
                session_id="sess_human",
                customer_id="cust_008",
                intent="CHURN_RISK",
                confidence=0.35,
                recent_events=[],
                features={},
            )

        assert result["action"] == "SEND_TO_HUMAN"
