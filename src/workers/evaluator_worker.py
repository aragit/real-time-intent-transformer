"""
Evaluator Background Worker
===========================
Periodic background task that runs the EvaluatorAgent to analyze
action efficacy and detect model drift.

Non-blocking async loop that runs independently of the main request
path. Designed to be started during application lifespan and cancelled
gracefully on shutdown.
"""

import asyncio

from loguru import logger

from src.agents.evaluator import close_evaluator, get_evaluator
from src.observability.metrics import (
    EVALUATOR_BATCH_ACTIONS,
    EVALUATOR_BATCH_CONVERSION_RATE,
    EVALUATOR_DRIFT_FLAGGED,
)


async def start_evaluator_loop(interval_seconds: int = 300, batch_size: int = 100) -> None:
    """
    Background loop that periodically runs evaluation batches.

    This coroutine runs for the lifetime of the application. It sleeps
    for `interval_seconds` between each batch to avoid overwhelming the
    database. Exceptions in individual batches are logged and do not
    terminate the loop.

    Args:
        interval_seconds: Time between evaluation batches (default: 300s = 5min).
        batch_size: Number of recent actions to evaluate per batch.
    """
    logger.info(f"Evaluator worker started (interval={interval_seconds}s, batch_size={batch_size})")

    evaluator = get_evaluator()

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            metrics = await evaluator.run_evaluation_batch(batch_size=batch_size)

            # Update Prometheus gauges for drift alerting
            EVALUATOR_DRIFT_FLAGGED.set(1 if metrics.drift_flagged else 0)
            EVALUATOR_BATCH_CONVERSION_RATE.set(metrics.conversion_rate)
            EVALUATOR_BATCH_ACTIONS.inc(metrics.actions_evaluated)

            if metrics.drift_flagged:
                logger.warning(
                    f"Evaluator flagged DRIFT: conversion={metrics.conversion_rate:.1%} "
                    f"(batch={metrics.batch_id[:8]}..)"
                )

        except asyncio.CancelledError:
            logger.info("Evaluator worker cancelled (shutdown)")
            break
        except Exception as e:
            logger.error(f"Evaluator batch failed: {e}")
            # Continue the loop — don't let one failure kill the worker

    logger.info("Evaluator worker stopped")


async def stop_evaluator_worker() -> None:
    """Clean up evaluator resources on shutdown."""
    await close_evaluator()
    logger.info("Evaluator worker resources released")
