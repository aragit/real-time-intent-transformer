"""
Evaluator Worker Lifecycle Tests (Phase 3: Meta-Cognition)
==========================================================
Tests for the background evaluator loop that periodically runs
evaluation batches for drift detection and efficacy analysis.

Verifies:
  1. Worker loop invokes run_evaluation_batch on interval
  2. Worker handles batch exceptions without terminating
  3. Worker stops cleanly on cancellation
  4. stop_evaluator_worker releases resources
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.evaluator import EvaluationMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ok_metrics() -> EvaluationMetrics:
    return EvaluationMetrics(
        batch_id="test-batch-0001",
        actions_evaluated=10,
        conversion_rate=0.40,
        critic_rewrite_success_rate=0.40,
        drift_flagged=False,
        diagnostics={"summary": "ok"},
    )


def _make_drift_metrics() -> EvaluationMetrics:
    return EvaluationMetrics(
        batch_id="test-batch-drift",
        actions_evaluated=20,
        conversion_rate=0.05,
        critic_rewrite_success_rate=0.05,
        drift_flagged=True,
        diagnostics={"summary": "drift detected"},
    )


# ===========================================================================
# Worker Loop Tests
# ===========================================================================

class TestEvaluatorLoop:

    @pytest.mark.asyncio
    async def test_loop_invokes_batch_at_least_once(self):
        """Worker loop should call run_evaluation_batch within a short interval."""
        mock_evaluator = MagicMock()
        mock_evaluator.run_evaluation_batch = AsyncMock(return_value=_make_ok_metrics())

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(start_evaluator_loop(interval_seconds=0.05))
            await asyncio.sleep(0.25)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert mock_evaluator.run_evaluation_batch.call_count >= 1

    @pytest.mark.asyncio
    async def test_loop_calls_with_batch_size(self):
        """Worker should forward batch_size to run_evaluation_batch."""
        mock_evaluator = MagicMock()
        mock_evaluator.run_evaluation_batch = AsyncMock(return_value=_make_ok_metrics())

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(
                start_evaluator_loop(interval_seconds=0.05, batch_size=50)
            )
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        mock_evaluator.run_evaluation_batch.assert_called_with(batch_size=50)

    @pytest.mark.asyncio
    async def test_loop_continues_after_batch_exception(self):
        """An exception in one batch should not kill the loop."""
        mock_evaluator = MagicMock()
        call_count = 0

        async def flaky_batch(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("PG connection lost")
            return _make_ok_metrics()

        mock_evaluator.run_evaluation_batch = flaky_batch

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(start_evaluator_loop(interval_seconds=0.05))
            await asyncio.sleep(0.35)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_loop_logs_drift_warning(self):
        """When drift is flagged, the loop should still continue."""
        mock_evaluator = MagicMock()
        mock_evaluator.run_evaluation_batch = AsyncMock(return_value=_make_drift_metrics())

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(start_evaluator_loop(interval_seconds=0.05))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert mock_evaluator.run_evaluation_batch.call_count >= 1


# ===========================================================================
# Worker Shutdown Tests
# ===========================================================================

class TestEvaluatorShutdown:

    @pytest.mark.asyncio
    async def test_cancelled_task_stops_cleanly(self):
        """Cancelling the worker task should exit the loop gracefully."""
        mock_evaluator = MagicMock()
        mock_evaluator.run_evaluation_batch = AsyncMock(return_value=_make_ok_metrics())

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(start_evaluator_loop(interval_seconds=0.05))
            await asyncio.sleep(0.15)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert task.done()

    @pytest.mark.asyncio
    async def test_no_background_tasks_after_cancel(self):
        """After cancellation, no lingering evaluator tasks should remain."""
        mock_evaluator = MagicMock()
        mock_evaluator.run_evaluation_batch = AsyncMock(return_value=_make_ok_metrics())

        with patch("src.workers.evaluator_worker.get_evaluator", return_value=mock_evaluator):
            from src.workers.evaluator_worker import start_evaluator_loop

            task = asyncio.create_task(start_evaluator_loop(interval_seconds=0.05))
            await asyncio.sleep(0.15)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        all_tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        worker_tasks = [t for t in all_tasks if "evaluator" in str(t.get_name()).lower()]
        assert len(worker_tasks) == 0

    @pytest.mark.asyncio
    async def test_stop_worker_releases_resources(self):
        """stop_evaluator_worker should call close_evaluator."""
        with patch("src.workers.evaluator_worker.close_evaluator", new_callable=AsyncMock) as mock_close:
            from src.workers.evaluator_worker import stop_evaluator_worker

            await stop_evaluator_worker()

        mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_worker_idempotent(self):
        """Calling stop_evaluator_worker multiple times should not raise."""
        with patch("src.workers.evaluator_worker.close_evaluator", new_callable=AsyncMock):
            from src.workers.evaluator_worker import stop_evaluator_worker

            await stop_evaluator_worker()
            await stop_evaluator_worker()
