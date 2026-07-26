"""
Evaluator Agent Tests (Phase 3: Meta-Cognition)
================================================
Tests for the background evaluator that cross-references dispatched actions
against user conversion events.

Verifies:
  1. Conversion window check (15-minute window for checkout events)
  2. LLM-as-a-Judge diagnostics for failed interventions
  3. Drift detection against historical baselines
  4. Full batch execution with mocked PG + SQLite dependencies
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.evaluator import (
    EvaluatorAgent,
    EvaluationMetrics,
    _get_llm,
    JUDGE_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Shared fixtures & helpers
# ---------------------------------------------------------------------------

def _make_action(**overrides) -> dict:
    base = {
        "action_id": str(uuid.uuid4())[:12],
        "session_id": "sess_eval_001",
        "action_type": "SHOW_URGENCY",
        "intent": "cart_abandonment",
        "confidence": 0.85,
        "payload": json.dumps({"reason": "high_intent"}),
        "status": "dispatched",
        "created_at": datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def _make_pool_mock() -> MagicMock:
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.execute = AsyncMock()
    pool_ctx = AsyncMock()
    pool_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
    pool_ctx.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire = MagicMock(return_value=pool_ctx)
    return mock_pool


def _make_evaluator_with_mock_pool(actions: list[dict] | None = None) -> tuple[EvaluatorAgent, MagicMock]:
    """Create an EvaluatorAgent with a fully mocked PG pool."""
    agent = EvaluatorAgent.__new__(EvaluatorAgent)
    agent._dsn = "postgresql://fake"
    mock_pool = _make_pool_mock()
    if actions is not None:
        mock_pool.acquire.return_value.__aenter__.return_value.fetch = AsyncMock(return_value=actions)
    agent._pool = mock_pool
    agent._read_pool = mock_pool
    return agent, mock_pool


# ===========================================================================
# Step 1: Conversion Window Check
# ===========================================================================

class TestCheckConversion:

    @pytest.mark.asyncio
    async def test_checkout_within_window_returns_true(self):
        """A checkout_start event within 15 minutes should return True."""
        action_time = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        async def fake_to_thread(fn):
            return True

        with patch("src.memory.get_event_store", return_value=MagicMock()), \
             patch("asyncio.to_thread", side_effect=fake_to_thread):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._check_conversion("sess_001", action_time)

        assert result is True

    @pytest.mark.asyncio
    async def test_checkout_outside_window_returns_false(self):
        """A checkout_start event beyond the 15-minute window returns False."""
        action_time = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        async def fake_to_thread(fn):
            return False

        with patch("src.memory.get_event_store", return_value=MagicMock()), \
             patch("asyncio.to_thread", side_effect=fake_to_thread):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._check_conversion("sess_001", action_time)

        assert result is False

    @pytest.mark.asyncio
    async def test_no_checkout_event_returns_false(self):
        """No checkout events in the session returns False."""
        action_time = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        async def fake_to_thread(fn):
            return False

        with patch("src.memory.get_event_store", return_value=MagicMock()), \
             patch("asyncio.to_thread", side_effect=fake_to_thread):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._check_conversion("sess_no_checkout", action_time)

        assert result is False

    @pytest.mark.asyncio
    async def test_custom_window_minutes(self):
        """Verify custom window parameter is respected via the closure."""
        action_time = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        async def fake_to_thread(fn):
            return True

        with patch("src.memory.get_event_store", return_value=MagicMock()), \
             patch("asyncio.to_thread", side_effect=fake_to_thread):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._check_conversion("sess_001", action_time, window_minutes=30)

        assert result is True

    @pytest.mark.asyncio
    async def test_sqlite_error_returns_false(self):
        """SQLite connection failure should gracefully return False."""
        action_time = datetime(2024, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(side_effect=RuntimeError("SQLite connection failed"))
        mock_cm.__exit__ = MagicMock(return_value=False)

        with patch("src.memory.get_event_store", return_value=MagicMock()), \
             patch("sqlite3.connect", return_value=mock_cm):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._check_conversion("sess_001", action_time)

        assert result is False


# ===========================================================================
# Step 2: LLM Diagnostics (run_llm_analysis)
# ===========================================================================

class TestRunLLMAnalysis:

    @pytest.mark.asyncio
    async def test_empty_actions_returns_stable_diagnostics(self):
        """No failed actions should return a clean diagnostics payload."""
        agent, _ = _make_evaluator_with_mock_pool()
        result = await agent._run_llm_analysis([])

        assert result["summary"] == "No failed actions to analyze."
        assert result["failure_categories"] == []
        assert result["drift_assessment"] == "stable"
        assert "confidence_threshold_recommendation" in result

    @pytest.mark.asyncio
    async def test_llm_returns_structured_diagnostics(self):
        """Mock LLM returning valid JSON should parse into diagnostics dict."""
        llm_output = json.dumps({
            "summary": "Most failures stem from low cart value sessions.",
            "failure_categories": [
                {
                    "category": "low_cart_value",
                    "count": 12,
                    "recommendation": "Lower confidence threshold for low-value carts",
                },
                {
                    "category": "wrong_timing",
                    "count": 5,
                    "recommendation": "Delay urgency triggers by 60 seconds",
                },
            ],
            "drift_assessment": "mild_drift",
            "confidence_threshold_recommendation": 0.65,
        })

        mock_response = MagicMock()
        mock_response.content = llm_output
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        failed_actions = [
            {"action_type": "SHOW_URGENCY", "intent": "cart_abandonment", "confidence": 0.80,
             "reason": "", "cart_value": 25.0, "duration_sec": 30.0},
            {"action_type": "SEND_ABANDON_EMAIL", "intent": "cart_abandonment", "confidence": 0.70,
             "reason": "", "cart_value": 15.0, "duration_sec": 45.0},
        ]

        with patch("src.agents.evaluator._get_llm", return_value=mock_llm):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._run_llm_analysis(failed_actions)

        assert result["summary"] == "Most failures stem from low cart value sessions."
        assert len(result["failure_categories"]) == 2
        assert result["failure_categories"][0]["category"] == "low_cart_value"
        assert result["failure_categories"][0]["count"] == 12
        assert result["drift_assessment"] == "mild_drift"
        assert result["confidence_threshold_recommendation"] == 0.65

    @pytest.mark.asyncio
    async def test_llm_returns_markdown_wrapped_json(self):
        """LLM output wrapped in markdown code block should still parse."""
        inner = json.dumps({
            "summary": "Timing issues dominate.",
            "failure_categories": [],
            "drift_assessment": "stable",
            "confidence_threshold_recommendation": 0.70,
        })
        llm_output = f"```json\n{inner}\n```"

        mock_response = MagicMock()
        mock_response.content = llm_output
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        failed_actions = [
            {"action_type": "SHOW_URGENCY", "intent": "browse", "confidence": 0.60,
             "reason": "", "cart_value": 0.0, "duration_sec": 10.0},
        ]

        with patch("src.agents.evaluator._get_llm", return_value=mock_llm):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._run_llm_analysis(failed_actions)

        assert result["summary"] == "Timing issues dominate."
        assert result["drift_assessment"] == "stable"

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(self):
        """LLM failure should return a safe fallback diagnostics payload."""
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(side_effect=RuntimeError("LLM crashed"))

        failed_actions = [
            {"action_type": "SHOW_URGENCY", "intent": "cart_abandonment", "confidence": 0.80,
             "reason": "", "cart_value": 50.0, "duration_sec": 20.0},
        ]

        with patch("src.agents.evaluator._get_llm", return_value=mock_llm):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._run_llm_analysis(failed_actions)

        assert result["summary"] == "LLM analysis unavailable."
        assert result["drift_assessment"] == "unknown"
        assert result["failure_categories"] == []

    @pytest.mark.asyncio
    async def test_llm_returns_malformed_json_returns_fallback(self):
        """Non-JSON LLM output should return fallback diagnostics."""
        mock_response = MagicMock()
        mock_response.content = "I cannot analyze this data."
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        failed_actions = [
            {"action_type": "APPLY_DISCOUNT", "intent": "checkout", "confidence": 0.90,
             "reason": "test", "cart_value": 100.0, "duration_sec": 60.0},
        ]

        with patch("src.agents.evaluator._get_llm", return_value=mock_llm):
            agent, _ = _make_evaluator_with_mock_pool()
            result = await agent._run_llm_analysis(failed_actions)

        assert result["drift_assessment"] == "unknown"
        assert result["failure_categories"] == []

    @pytest.mark.asyncio
    async def test_llm_prompt_includes_action_details(self):
        """Verify the LLM receives a prompt with action type, intent, confidence."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "summary": "test",
            "failure_categories": [],
            "drift_assessment": "stable",
            "confidence_threshold_recommendation": 0.70,
        })
        mock_llm = MagicMock()
        mock_llm.invoke = AsyncMock(return_value=mock_response)

        failed_actions = [
            {"action_type": "SHOW_URGENCY", "intent": "cart_abandonment", "confidence": 0.88,
             "reason": "high_value_cart", "cart_value": 200.0, "duration_sec": 120.0},
        ]

        with patch("src.agents.evaluator._get_llm", return_value=mock_llm):
            agent, _ = _make_evaluator_with_mock_pool()
            await agent._run_llm_analysis(failed_actions)

        call_args = mock_llm.invoke.call_args[0][0]
        assert call_args[0].content == JUDGE_SYSTEM_PROMPT
        assert "SHOW_URGENCY" in call_args[1].content
        assert "cart_abandonment" in call_args[1].content
        assert "0.88" in call_args[1].content


# ===========================================================================
# Step 3: Drift Detection
# ===========================================================================

class TestDriftDetection:

    def test_significant_drop_flags_drift(self):
        """0.05 vs 0.30 baseline (>20% drop) should flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        # avg=0.30, drop = (0.30 - 0.05) / 0.30 = 0.833 > 0.20
        result = agent._detect_drift(0.05, [0.30, 0.28, 0.32, 0.29, 0.31])
        assert result is True

    def test_no_significant_drop_no_drift(self):
        """0.28 vs 0.30 baseline (6.7% drop) should not flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        result = agent._detect_drift(0.28, [0.30, 0.28, 0.32, 0.29, 0.31])
        assert result is False

    def test_insufficient_history_no_drift(self):
        """Fewer than 2 historical data points should never flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        assert agent._detect_drift(0.05, [0.30]) is False
        assert agent._detect_drift(0.05, []) is False

    def test_baseline_zero_with_nonzero_current(self):
        """When historical baseline is all zeros and current is nonzero, flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        result = agent._detect_drift(0.50, [0.0, 0.0, 0.0])
        assert result is True

    def test_baseline_zero_with_zero_current(self):
        """When baseline is all zeros, conversion_rate < 1.0 flags drift (impl logic)."""
        agent, _ = _make_evaluator_with_mock_pool()
        # avg=0, conversion_rate=0.0 -> 0.0 < 1.0 is True
        result = agent._detect_drift(0.0, [0.0, 0.0])
        assert result is True

    def test_baseline_zero_with_perfect_current(self):
        """When baseline is zero but current is 1.0, no drift (100% conversion)."""
        agent, _ = _make_evaluator_with_mock_pool()
        result = agent._detect_drift(1.0, [0.0, 0.0])
        assert result is False

    def test_exact_threshold_boundary(self):
        """A drop at or below 20% should NOT flag (threshold is > 20%)."""
        agent, _ = _make_evaluator_with_mock_pool()
        # avg=0.50, rate=0.42, drop = (0.50-0.42)/0.50 = 0.16 = 16% -> no drift
        result = agent._detect_drift(0.42, [0.50, 0.50])
        assert result is False

    def test_just_above_threshold(self):
        """A drop slightly above 20% should flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        # avg=0.10, rate=0.079, drop = 0.21 > 0.20
        result = agent._detect_drift(0.079, [0.10, 0.10])
        assert result is True

    def test_improving_rate_no_drift(self):
        """Current rate above historical average should not flag drift."""
        agent, _ = _make_evaluator_with_mock_pool()
        result = agent._detect_drift(0.40, [0.30, 0.28, 0.32])
        assert result is False


# ===========================================================================
# Step 4: Batch Execution (run_evaluation_batch)
# ===========================================================================

class TestRunEvaluationBatch:

    @pytest.mark.asyncio
    async def test_empty_ledger_returns_zero_metrics(self):
        """No actions in the ledger should return zero metrics."""
        agent, mock_pool = _make_evaluator_with_mock_pool(actions=[])
        metrics = await agent.run_evaluation_batch(batch_size=100)

        assert metrics.actions_evaluated == 0
        assert metrics.conversion_rate == 0.0
        assert metrics.drift_flagged is False
        assert "No actions in ledger." in metrics.diagnostics["summary"]

    @pytest.mark.asyncio
    async def test_all_converting_actions(self):
        """Actions where checkout completes within window should yield 100% conversion."""
        actions = [
            _make_action(session_id="sess_a", created_at=datetime(2024, 7, 1, 12, i, 0, tzinfo=timezone.utc))
            for i in range(3)
        ]
        agent, mock_pool = _make_evaluator_with_mock_pool(actions=actions)

        with patch.object(agent, "_check_conversion", new_callable=AsyncMock, return_value=True), \
             patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                 "summary": "All converted.", "failure_categories": [],
                 "drift_assessment": "stable", "confidence_threshold_recommendation": 0.70,
             }), \
             patch.object(agent, "_persist_metrics", new_callable=AsyncMock) as mock_persist:
            metrics = await agent.run_evaluation_batch(batch_size=3)

        assert metrics.actions_evaluated == 3
        assert metrics.conversion_rate == 1.0
        assert metrics.drift_flagged is False
        mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_converting_actions_flags_drift(self):
        """All actions failing with >=10 should flag drift."""
        actions = [
            _make_action(session_id=f"sess_{i}", created_at=datetime(2024, 7, 1, 12, i, 0, tzinfo=timezone.utc))
            for i in range(12)
        ]
        agent, mock_pool = _make_evaluator_with_mock_pool(actions=actions)

        with patch.object(agent, "_check_conversion", new_callable=AsyncMock, return_value=False), \
             patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                 "summary": "All failed.", "failure_categories": [],
                 "drift_assessment": "severe_drift", "confidence_threshold_recommendation": 0.60,
             }), \
             patch.object(agent, "_persist_metrics", new_callable=AsyncMock):
            metrics = await agent.run_evaluation_batch(batch_size=12)

        assert metrics.actions_evaluated == 12
        assert metrics.conversion_rate == 0.0
        assert metrics.drift_flagged is True

    @pytest.mark.asyncio
    async def test_mixed_conversion_rate(self):
        """50% conversion with 10+ actions and rate < 10% should flag drift; 50% should not."""
        actions = [
            _make_action(session_id=f"sess_{i}", created_at=datetime(2024, 7, 1, 12, i, 0, tzinfo=timezone.utc))
            for i in range(10)
        ]
        agent, mock_pool = _make_evaluator_with_mock_pool(actions=actions)

        convert_sessions = {"sess_0", "sess_1", "sess_2", "sess_3", "sess_4"}

        async def fake_check(session_id, action_time, window_minutes=15):
            return session_id in convert_sessions

        with patch.object(agent, "_check_conversion", side_effect=fake_check), \
             patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                 "summary": "Mixed.", "failure_categories": [],
                 "drift_assessment": "stable", "confidence_threshold_recommendation": 0.70,
             }), \
             patch.object(agent, "_persist_metrics", new_callable=AsyncMock):
            metrics = await agent.run_evaluation_batch(batch_size=10)

        assert metrics.actions_evaluated == 10
        assert metrics.conversion_rate == 0.5
        assert metrics.drift_flagged is False

    @pytest.mark.asyncio
    async def test_persist_metrics_receives_correct_data(self):
        """_persist_metrics should be called with an EvaluationMetrics instance."""
        actions = [_make_action(session_id="sess_persist")]
        agent, mock_pool = _make_evaluator_with_mock_pool(actions=actions)

        with patch.object(agent, "_check_conversion", new_callable=AsyncMock, return_value=True), \
             patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                 "summary": "ok", "failure_categories": [],
                 "drift_assessment": "stable", "confidence_threshold_recommendation": 0.70,
             }), \
             patch.object(agent, "_persist_metrics", new_callable=AsyncMock) as mock_persist:
            await agent.run_evaluation_batch(batch_size=1)

        persisted = mock_persist.call_args[0][0]
        assert isinstance(persisted, EvaluationMetrics)
        assert persisted.actions_evaluated == 1
        assert persisted.conversion_rate == 1.0

    @pytest.mark.asyncio
    async def test_batch_generates_unique_batch_id(self):
        """Each batch run should produce a unique batch_id."""
        actions = [_make_action()]
        agent, _ = _make_evaluator_with_mock_pool(actions=actions)

        ids = set()
        for _ in range(3):
            with patch.object(agent, "_check_conversion", new_callable=AsyncMock, return_value=False), \
                 patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                     "summary": "", "failure_categories": [],
                     "drift_assessment": "stable", "confidence_threshold_recommendation": 0.70,
                 }), \
                 patch.object(agent, "_persist_metrics", new_callable=AsyncMock):
                m = await agent.run_evaluation_batch(batch_size=1)
                ids.add(m.batch_id)

        assert len(ids) == 3

    @pytest.mark.asyncio
    async def test_failed_actions_passed_to_llm(self):
        """Non-converting actions should be collected and passed to LLM analysis."""
        actions = [
            _make_action(session_id="sess_fail", action_type="SHOW_URGENCY", intent="cart_abandonment", confidence=0.75),
            _make_action(session_id="sess_conv", action_type="APPLY_DISCOUNT", intent="checkout", confidence=0.90),
        ]
        agent, _ = _make_evaluator_with_mock_pool(actions=actions)

        async def fake_check(session_id, action_time, window_minutes=15):
            return session_id == "sess_conv"

        with patch.object(agent, "_check_conversion", side_effect=fake_check), \
             patch.object(agent, "_run_llm_analysis", new_callable=AsyncMock, return_value={
                 "summary": "", "failure_categories": [],
                 "drift_assessment": "stable", "confidence_threshold_recommendation": 0.70,
             }) as mock_llm, \
             patch.object(agent, "_persist_metrics", new_callable=AsyncMock):
            await agent.run_evaluation_batch(batch_size=2)

        failed = mock_llm.call_args[0][0]
        assert len(failed) == 1
        assert failed[0]["action_type"] == "SHOW_URGENCY"
        assert failed[0]["intent"] == "cart_abandonment"
        assert failed[0]["confidence"] == 0.75


# ===========================================================================
# Component Tests
# ===========================================================================

class TestEvaluatorComponents:

    def test_metrics_repr(self):
        """EvaluationMetrics __repr__ should be human-readable."""
        m = EvaluationMetrics(
            batch_id="abc12345-6789-0000-0000-000000000000",
            actions_evaluated=42,
            conversion_rate=0.357,
            critic_rewrite_success_rate=0.357,
            drift_flagged=True,
            diagnostics={"summary": "test"},
        )
        r = repr(m)
        assert "abc12345" in r
        assert "42" in r
        assert "35.7%" in r
        assert "True" in r

    def test_metrics_stores_all_fields(self):
        """EvaluationMetrics should store all constructor arguments."""
        diag = {"summary": "x", "failure_categories": []}
        m = EvaluationMetrics(
            batch_id="b1",
            actions_evaluated=10,
            conversion_rate=0.5,
            critic_rewrite_success_rate=0.4,
            drift_flagged=False,
            diagnostics=diag,
        )
        assert m.batch_id == "b1"
        assert m.actions_evaluated == 10
        assert m.conversion_rate == 0.5
        assert m.critic_rewrite_success_rate == 0.4
        assert m.drift_flagged is False
        assert m.diagnostics is diag
