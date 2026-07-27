"""
Critic Agent Tests
==================
Tests for the LLM Verifier & Deterministic Governance layer.

Verifies the 3-tier safety gate:
  1. Approval (OPA allows → action passes through unchanged)
  2. Rewrite (OPA denies → LLM rewrites to compliant fallback)
  3. Hard Rejection (OPA denies + LLM fails → NO_ACTION)

All external dependencies (OPA, LLM) are fully mocked.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.critic import CRITIC_SYSTEM_PROMPT, run_critic

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_features(**overrides) -> dict:
    base = {
        "total_cart_value": 150.0,
        "cart_adds": 3,
        "checkouts": 0,
        "session_duration_sec": 120,
        "inventory_level": 25,
        "intent": "CHECKOUT_INTENT",
    }
    base.update(overrides)
    return base


def _make_mock_opa(allowed: bool) -> MagicMock:
    mock_opa = MagicMock()
    mock_opa.evaluate = AsyncMock(return_value=allowed)
    return mock_opa


def _make_mock_llm(output: str) -> MagicMock:
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = output
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


# ---------------------------------------------------------------------------
# Scenario 1: OPA Approval — action passes through unchanged
# ---------------------------------------------------------------------------


class TestCriticApproval:
    @pytest.mark.asyncio
    async def test_opa_approved_returns_proposed_action(self):
        mock_opa = _make_mock_opa(allowed=True)

        result = await run_critic(
            proposed_action="APPLY_DISCOUNT",
            session_id="sess_approve",
            customer_id="cust_001",
            confidence=0.85,
            reasoning="Customer shows high purchase intent",
            product_context="Electronics category",
            customer_segment="premium",
            features=_make_features(),
            opa_client=mock_opa,
        )

        assert result["action"] == "APPLY_DISCOUNT"
        assert result["source"] == "system_2_critic_approved"
        assert result["opa_allowed"] is True

    @pytest.mark.asyncio
    async def test_opa_approved_preserves_planner_reasoning(self):
        mock_opa = _make_mock_opa(allowed=True)
        planner_reasoning = "High-value cart with 3 items, checkout intent detected"

        result = await run_critic(
            proposed_action="OFFER_BUNDLE",
            session_id="sess_reason",
            customer_id="cust_002",
            confidence=0.78,
            reasoning=planner_reasoning,
            product_context="Laptop + accessories",
            customer_segment="tech_enthusiast",
            features=_make_features(),
            opa_client=mock_opa,
        )

        assert result["reasoning"] == planner_reasoning
        assert result["action"] == "OFFER_BUNDLE"

    @pytest.mark.asyncio
    async def test_opa_approved_never_calls_llm(self):
        mock_opa = _make_mock_opa(allowed=True)

        with patch("src.agents.critic._get_llm") as mock_get_llm:
            await run_critic(
                proposed_action="SHOW_URGENCY",
                session_id="sess_nollm",
                customer_id="cust_003",
                confidence=0.90,
                reasoning="Low stock urgency",
                product_context="Limited item",
                customer_segment="impulse_buyer",
                features=_make_features(),
                opa_client=mock_opa,
            )

            mock_get_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_opa_evaluation_called_with_correct_args(self):
        mock_opa = _make_mock_opa(allowed=True)
        customer = {"customer_id": "cust_005"}
        features = _make_features(total_cart_value=200.0)

        await run_critic(
            proposed_action="APPLY_DISCOUNT",
            session_id="sess_args",
            customer_id="cust_005",
            confidence=0.72,
            reasoning="Testing argument passing",
            product_context="",
            customer_segment="regular",
            features=features,
            opa_client=mock_opa,
        )

        mock_opa.evaluate.assert_called_once_with(
            "APPLY_DISCOUNT",
            customer,
            features,
        )


# ---------------------------------------------------------------------------
# Scenario 2: OPA Denial + LLM Rewrite → compliant fallback
# ---------------------------------------------------------------------------


class TestCriticRewrite:
    @pytest.mark.asyncio
    async def test_opa_denied_llm_rewrites_action(self):
        mock_opa = _make_mock_opa(allowed=False)
        llm_output = json.dumps(
            {
                "action": "FREE_SHIPPING",
                "reasoning": "Discount exceeds policy cap; offering free shipping as compliant alternative",
            }
        )
        mock_llm = _make_mock_llm(llm_output)

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="APPLY_DISCOUNT",
                session_id="sess_rewrite",
                customer_id="cust_010",
                confidence=0.65,
                reasoning="Customer price-sensitive, needs incentive",
                product_context="Cart value $150",
                customer_segment="price_sensitive",
                features=_make_features(total_cart_value=150.0),
                opa_client=mock_opa,
            )

        assert result["action"] == "FREE_SHIPPING"
        assert result["source"] == "system_2_critic_rewrite"
        assert result["opa_allowed"] is False
        assert "Critic rewrite" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_llm_called_with_correct_prompt_structure(self):
        mock_opa = _make_mock_opa(allowed=False)
        llm_output = json.dumps(
            {
                "action": "NO_ACTION",
                "reasoning": "No compliant alternative available",
            }
        )
        mock_llm = _make_mock_llm(llm_output)

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            await run_critic(
                proposed_action="APPLY_DISCOUNT",
                session_id="sess_prompt",
                customer_id="cust_011",
                confidence=0.55,
                reasoning="Discount requested",
                product_context="Electronics",
                customer_segment="bargain_hunter",
                features=_make_features(total_cart_value=80.0),
                opa_client=mock_opa,
            )

        mock_llm.ainvoke.assert_called_once()
        call_args = mock_llm.ainvoke.call_args[0][0]
        # First message is system prompt, second is human with context
        assert call_args[0].content == CRITIC_SYSTEM_PROMPT
        assert "APPLY_DISCOUNT" in call_args[1].content
        assert "cust_011" in call_args[1].content
        assert "bargain_hunter" in call_args[1].content

    @pytest.mark.asyncio
    async def test_rewrite_returns_sends_abandon_email(self):
        mock_opa = _make_mock_opa(allowed=False)
        llm_output = json.dumps(
            {
                "action": "SEND_ABANDON_EMAIL",
                "reasoning": "Customer abandoned cart; recovery email is policy-compliant",
            }
        )
        mock_llm = _make_mock_llm(llm_output)

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="OFFER_DISCOUNT",
                session_id="sess_abandon",
                customer_id="cust_012",
                confidence=0.45,
                reasoning="Cart abandonment risk",
                product_context="",
                customer_segment="at_risk",
                features=_make_features(cart_adds=2, checkouts=0),
                opa_client=mock_opa,
            )

        assert result["action"] == "SEND_ABANDON_EMAIL"
        assert result["source"] == "system_2_critic_rewrite"

    @pytest.mark.asyncio
    async def test_rewrite_handles_llm_json_in_markdown_block(self):
        mock_opa = _make_mock_opa(allowed=False)
        llm_output = f"""Here's the compliant alternative:

```json
{
            json.dumps(
                {
                    "action": "LOYALTY_REWARD",
                    "reasoning": "Offering loyalty points instead of discount",
                }
            )
        }
```
"""
        mock_llm = _make_mock_llm(llm_output)

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="APPLY_DISCOUNT",
                session_id="sess_markdown",
                customer_id="cust_013",
                confidence=0.70,
                reasoning="Loyalty customer",
                product_context="",
                customer_segment="loyal",
                features=_make_features(),
                opa_client=mock_opa,
            )

        assert result["action"] == "LOYALTY_REWARD"
        assert result["source"] == "system_2_critic_rewrite"


# ---------------------------------------------------------------------------
# Scenario 3: Hard Rejection — OPA denies + LLM fails → NO_ACTION
# ---------------------------------------------------------------------------


class TestCriticHardRejection:
    @pytest.mark.asyncio
    async def test_llm_timeout_returns_no_action(self):
        mock_opa = _make_mock_opa(allowed=False)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=TimeoutError("LLM request timed out"))

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="APPLY_DISCOUNT",
                session_id="sess_timeout",
                customer_id="cust_020",
                confidence=0.60,
                reasoning="Discount needed",
                product_context="",
                customer_segment="regular",
                features=_make_features(),
                opa_client=mock_opa,
            )

        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_critic_rejected"
        assert result["opa_allowed"] is False
        assert "policy violation" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_llm_connection_error_returns_no_action(self):
        mock_opa = _make_mock_opa(allowed=False)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=ConnectionError("Cannot reach Ollama server"))

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="OFFER_DISCOUNT",
                session_id="sess_conn_err",
                customer_id="cust_021",
                confidence=0.55,
                reasoning="Price incentive",
                product_context="",
                customer_segment="price_sensitive",
                features=_make_features(),
                opa_client=mock_opa,
            )

        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_critic_rejected"

    @pytest.mark.asyncio
    async def test_llm_malformed_output_returns_no_action(self):
        mock_opa = _make_mock_opa(allowed=False)
        # LLM returns text with no JSON
        mock_llm = _make_mock_llm("I cannot determine a compliant action for this case.")

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="APPLY_DISCOUNT",
                session_id="sess_malformed",
                customer_id="cust_022",
                confidence=0.50,
                reasoning="Discount requested",
                product_context="",
                customer_segment="unknown",
                features=_make_features(),
                opa_client=mock_opa,
            )

        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_critic_rejected"
        assert result["opa_allowed"] is False

    @pytest.mark.asyncio
    async def test_opa_failure_treated_as_denial(self):
        # OPA client raises an exception (service unreachable)
        mock_opa = MagicMock()
        mock_opa.evaluate = AsyncMock(side_effect=ConnectionError("OPA service unreachable"))

        result = await run_critic(
            proposed_action="SHOW_URGENCY",
            session_id="sess_opa_fail",
            customer_id="cust_023",
            confidence=0.80,
            reasoning="Urgency signal detected",
            product_context="Low stock",
            customer_segment="impulse",
            features=_make_features(),
            opa_client=mock_opa,
        )

        # When OPA fails, action is denied (fail-safe)
        assert result["opa_allowed"] is False
        # LLM also not called (no mock set up for it, so it falls to NO_ACTION)
        assert result["action"] == "NO_ACTION"
        assert result["source"] == "system_2_critic_rejected"

    @pytest.mark.asyncio
    async def test_includes_original_action_in_rejection_reason(self):
        mock_opa = _make_mock_opa(allowed=False)
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM crashed"))

        with patch("src.agents.critic._get_llm", return_value=mock_llm):
            result = await run_critic(
                proposed_action="OFFER_DISCOUNT",
                session_id="sess_reason",
                customer_id="cust_024",
                confidence=0.40,
                reasoning="Deep discount needed",
                product_context="",
                customer_segment="churning",
                features=_make_features(),
                opa_client=mock_opa,
            )

        assert "OFFER_DISCOUNT" in result["reasoning"]
        assert "policy violation" in result["reasoning"]


# ---------------------------------------------------------------------------
# Unit tests for helper components
# ---------------------------------------------------------------------------


class TestCriticComponents:
    def test_system_prompt_enforces_json_format(self):
        assert "JSON" in CRITIC_SYSTEM_PROMPT
        assert '{"action"' in CRITIC_SYSTEM_PROMPT

    def test_system_prompt_blocks_discount_actions(self):
        assert "APPLY_DISCOUNT" in CRITIC_SYSTEM_PROMPT
        assert "OFFER_DISCOUNT" in CRITIC_SYSTEM_PROMPT
        assert "CANNOT" in CRITIC_SYSTEM_PROMPT

    def test_system_prompt_lists_compliant_actions(self):
        compliant = [
            "NO_ACTION",
            "SHOW_URGENCY",
            "SEND_ABANDON_EMAIL",
            "OFFER_BUNDLE",
            "SEND_TO_HUMAN",
            "LOYALTY_REWARD",
            "RECOMMEND_ALTERNATIVE",
        ]
        for action in compliant:
            assert action in CRITIC_SYSTEM_PROMPT
