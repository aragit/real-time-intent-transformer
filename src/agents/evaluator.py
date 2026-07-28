"""
Evaluator Agent (Phase 3: Meta-Cognition)
==========================================
Background agent that evaluates action efficacy by cross-referencing
dispatched actions against actual user conversion events.

Runs offline against PostgreSQL, analyzing the action_ledger to:
  - Calculate conversion success rates per action type
  - Detect model drift (declining efficacy over time)
  - Use LLM-as-a-Judge to diagnose failed interventions
  - Persist aggregated metrics to evaluation_metrics table

This is the closed-loop feedback that enables the system to self-improve.
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

import asyncpg
from loguru import logger

from langfuse.decorators import observe
from src.config import settings

# Lazy-initialized components
_llm = None
_evaluator: Optional["EvaluatorAgent"] = None

# Concurrency semaphore for LLM calls to prevent OOM under burst traffic.
_llm_semaphore: asyncio.Semaphore | None = None

LLM_TIMEOUT_SECONDS = 30.0
LLM_MAX_CONCURRENCY = 10


METRICS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id                      BIGSERIAL PRIMARY KEY,
    batch_id                TEXT NOT NULL,
    actions_evaluated       INTEGER NOT NULL,
    conversion_rate         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    critic_rewrite_success_rate DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    drift_flagged           BOOLEAN NOT NULL DEFAULT FALSE,
    diagnostics             JSONB DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_eval_metrics_batch
    ON evaluation_metrics (batch_id);

CREATE INDEX IF NOT EXISTS idx_eval_metrics_created
    ON evaluation_metrics (created_at DESC);
"""


def _get_llm():
    """Get or create the LLM client for drift analysis."""
    global _llm
    if _llm is None:
        if settings.llm_provider == "ollama":
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from langchain_community.chat_models import ChatOllama

            _llm = ChatOllama(
                model=settings.llm_model,
                base_url=settings.llm_base_url.replace("/v1", ""),
            )
        else:
            from langchain_openai import ChatOpenAI

            _llm = ChatOpenAI(
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                temperature=0.2,
                max_tokens=512,
            )
        logger.info(f"Evaluator LLM initialized: {settings.llm_provider}/{settings.llm_model}")
    return _llm


def _get_llm_semaphore() -> asyncio.Semaphore:
    """Get or create the shared LLM concurrency semaphore."""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(LLM_MAX_CONCURRENCY)
    return _llm_semaphore


JUDGE_SYSTEM_PROMPT = """You are an e-commerce intervention evaluator.

Your job is to analyze why a dispatched intervention failed to convert.

## Context
You receive a list of actions that did NOT lead to user conversion.
For each action, you see:
- The action type (e.g., SHOW_URGENCY, SEND_ABANDON_EMAIL)
- The intent it was targeting
- The confidence score
- Session features (cart value, duration, etc.)

## Your Task
Analyze the batch and provide:
1. A summary of the most common failure patterns
2. Specific recommendations for each failure category
3. An overall drift assessment (are interventions becoming less effective?)

## Output Format
Return a JSON object:
{
  "summary": "<one-paragraph summary of failure patterns>",
  "failure_categories": [
    {
      "category": "<e.g., wrong_timing, low_cart_value, intent_mismatch>",
      "count": <number>,
      "recommendation": "<specific fix>"
    }
  ],
  "drift_assessment": "<one of: stable, mild_drift, severe_drift>",
  "confidence_threshold_recommendation": <float between 0.3 and 0.9>
}
"""


class EvaluationMetrics:
    """Parsed evaluation metrics from a batch run."""

    def __init__(
        self,
        batch_id: str,
        actions_evaluated: int,
        conversion_rate: float,
        critic_rewrite_success_rate: float,
        drift_flagged: bool,
        diagnostics: dict,
    ):
        self.batch_id = batch_id
        self.actions_evaluated = actions_evaluated
        self.conversion_rate = conversion_rate
        self.critic_rewrite_success_rate = critic_rewrite_success_rate
        self.drift_flagged = drift_flagged
        self.diagnostics = diagnostics

    def __repr__(self) -> str:
        return (
            f"EvalMetrics(batch={self.batch_id[:8]}.., "
            f"n={self.actions_evaluated}, "
            f"conv={self.conversion_rate:.1%}, "
            f"drift={self.drift_flagged})"
        )


class EvaluatorAgent:
    """
    Background evaluator that analyzes action efficacy.

    Connects to PostgreSQL for reading the action_ledger and writing
    evaluation_metrics. Uses the local event store for outcome correlation.

    Reads route to the configured read-replica (if set) to avoid lock
    contention with the System 1 hot-path.
    """

    def __init__(self, pg_dsn: str | None = None):
        self._dsn = pg_dsn or settings.postgres_dsn
        self._pool: asyncpg.Pool | None = None
        self._read_pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Lazy-initialize the asyncpg connection pool (primary, for writes)."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=1,
                max_size=3,
            )
            await self._init_metrics_schema()
            logger.info("EvaluatorAgent primary pool connected")
        return self._pool

    async def _get_read_pool(self) -> asyncpg.Pool:
        """Lazy-initialize the read-replica pool (for SELECT queries)."""
        if self._read_pool is None:
            replica_dsn = settings.postgres_read_replica_dsn or self._dsn
            self._read_pool = await asyncpg.create_pool(
                replica_dsn,
                min_size=1,
                max_size=3,
            )
            logger.info(
                f"EvaluatorAgent read pool connected "
                f"({'replica' if settings.postgres_read_replica_dsn else 'primary'})"
            )
        return self._read_pool

    async def _init_metrics_schema(self) -> None:
        """Create evaluation_metrics table if it doesn't exist."""
        if self._pool is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(METRICS_SCHEMA_SQL)

    async def _fetch_recent_actions(self, batch_size: int) -> list[dict]:
        """
        Fetch the last batch_size actions from the action_ledger.

        Uses the read-replica pool to avoid lock contention with hot-path writes.
        Returns raw rows as dicts for flexible downstream processing.
        """
        pool = await self._get_read_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT action_id, session_id, action_type, intent,
                       confidence, payload, status, created_at
                FROM action_ledger
                ORDER BY created_at DESC
                LIMIT $1
                """,
                batch_size,
            )
        return [dict(r) for r in rows]

    async def _check_conversion(
        self,
        session_id: str,
        action_time: datetime,
        window_minutes: int = 15,
    ) -> bool | None:
        """
        Check if a checkout occurred within the window after the action.

        Returns True if converted, False if not converted, None if the
        observation window has not yet elapsed (action too recent to evaluate).
        """
        now = datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        buffer_minutes = 5
        if (now - action_time) <= timedelta(minutes=window_minutes + buffer_minutes):
            return None

        def _sync_check() -> bool:
            import sqlite3

            from src.config import settings as cfg

            db_path = cfg.database_url.replace("sqlite:///", "")
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    window_end = action_time + timedelta(minutes=window_minutes)
                    rows = conn.execute(
                        """
                        SELECT action FROM events
                        WHERE session_id = ?
                          AND timestamp >= ?
                          AND timestamp <= ?
                        ORDER BY timestamp
                        """,
                        (
                            session_id,
                            action_time.isoformat(),
                            window_end.isoformat(),
                        ),
                    ).fetchall()
                    for row in rows:
                        if row["action"] in ("checkout_start", "purchase_complete"):
                            return True
                    return False
            except Exception as e:
                logger.warning(f"Conversion check failed for session {session_id}: {e}")
                return False

        return await asyncio.to_thread(_sync_check)

    @observe(as_type="generation")
    async def _run_llm_analysis(self, failed_actions: list[dict]) -> dict:
        """
        Use the local LLM to analyze failed interventions.

        Returns parsed JSON diagnostics from the LLM.
        """
        if not failed_actions:
            return {
                "summary": "No failed actions to analyze.",
                "failure_categories": [],
                "drift_assessment": "stable",
                "confidence_threshold_recommendation": settings.system_2_confidence_threshold,
            }

        # Build a concise prompt from the failed actions
        action_summary = "\n".join(
            f"  - {a['action_type']} (intent={a['intent']}, "
            f"conf={a['confidence']:.2f}, cart=${a.get('cart_value', 0):.2f}, "
            f"duration={a.get('duration_sec', 0):.0f}s)"
            for a in failed_actions[:20]  # Limit to 20 for token budget
        )

        user_prompt = (
            f"Analyze these {len(failed_actions)} failed interventions:\n"
            f"{action_summary}\n\n"
            f"Provide your analysis as JSON."
        )

        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = _get_llm()
            sem = _get_llm_semaphore()
            async with sem:
                response = await asyncio.wait_for(
                    llm.ainvoke(
                        [
                            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                            HumanMessage(content=user_prompt),
                        ]
                    ),
                    timeout=LLM_TIMEOUT_SECONDS,
                )

            output = response.content if hasattr(response, "content") else str(response)

            # Parse JSON from LLM output
            match = re.search(r"\{.*\}", output, re.DOTALL)
            if match:
                return json.loads(match.group())

        except Exception as e:
            logger.warning(f"LLM drift analysis failed: {e}")

        return {
            "summary": "LLM analysis unavailable.",
            "failure_categories": [],
            "drift_assessment": "unknown",
            "confidence_threshold_recommendation": settings.system_2_confidence_threshold,
        }

    def _detect_drift(self, conversion_rate: float, history: list[float]) -> bool:
        """
        Detect if conversion rate has dropped significantly.

        Compares current batch rate against the rolling average
        of previous batches. Flags drift if current rate is >20%
        below the historical average.
        """
        if len(history) < 2:
            return False

        avg = sum(history) / len(history)
        if avg == 0:
            return conversion_rate < 1.0

        drop_pct = (avg - conversion_rate) / avg
        return drop_pct > 0.20

    @observe()
    async def run_evaluation_batch(
        self,
        batch_size: int = 100,
    ) -> EvaluationMetrics:
        """
        Run a single evaluation batch.

        1. Fetch recent actions from PG ledger
        2. Correlate each action with subsequent user events
        3. Run LLM analysis on non-converting actions
        4. Compute and persist aggregated metrics

        Returns the computed EvaluationMetrics.
        """
        batch_id = str(uuid.uuid4())
        logger.info(f"Starting evaluation batch {batch_id[:8]}.. (size={batch_size})")

        # Step 1: Fetch recent actions
        actions = await self._fetch_recent_actions(batch_size)
        if not actions:
            logger.info("No actions found in ledger. Skipping batch.")
            return EvaluationMetrics(
                batch_id=batch_id,
                actions_evaluated=0,
                conversion_rate=0.0,
                critic_rewrite_success_rate=0.0,
                drift_flagged=False,
                diagnostics={"summary": "No actions in ledger."},
            )

        # Step 2: Outcome correlation
        converted = 0
        failed_actions = []

        for action in actions:
            session_id = action["session_id"]
            action_time = action["created_at"]
            # Ensure action_time is timezone-aware
            if action_time.tzinfo is None:
                action_time = action_time.replace(tzinfo=UTC)

            is_converted = await self._check_conversion(session_id, action_time)

            if is_converted is None:
                continue
            elif is_converted:
                converted += 1
            else:
                # Collect failed action details for LLM analysis
                payload = action.get("payload", {})
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        payload = {}

                failed_actions.append(
                    {
                        "action_type": action["action_type"],
                        "intent": action["intent"],
                        "confidence": action["confidence"],
                        "reason": payload.get("reason", ""),
                        "cart_value": 0.0,  # Not stored in ledger payload
                        "duration_sec": 0.0,
                    }
                )

        conversion_rate = converted / len(actions) if actions else 0.0

        # Step 3: LLM-as-a-Judge drift analysis
        diagnostics = await self._run_llm_analysis(failed_actions)

        # Step 4: Drift detection using historical batches
        try:
            recent = await self.get_recent_metrics(limit=20)
            history = [m["conversion_rate"] for m in recent if m.get("conversion_rate") is not None]
        except Exception:
            history = []
        drift_flagged = self._detect_drift(conversion_rate, history)
        if not drift_flagged and not history and conversion_rate < 0.10 and len(actions) >= 10:
            drift_flagged = True

        # Step 5: Compute critic rewrite success rate
        # This is a placeholder — in a full implementation, we'd track
        # which actions originated from critic rewrites vs. approvals
        critic_rewrite_success_rate = conversion_rate

        metrics = EvaluationMetrics(
            batch_id=batch_id,
            actions_evaluated=len(actions),
            conversion_rate=conversion_rate,
            critic_rewrite_success_rate=critic_rewrite_success_rate,
            drift_flagged=drift_flagged,
            diagnostics=diagnostics,
        )

        # Step 6: Persist metrics
        await self._persist_metrics(metrics)

        logger.info(
            f"Batch {batch_id[:8]}.. complete: "
            f"{len(actions)} actions, "
            f"{conversion_rate:.1%} conversion, "
            f"drift={drift_flagged}"
        )

        return metrics

    async def _persist_metrics(self, metrics: EvaluationMetrics) -> None:
        """Save evaluation metrics to PostgreSQL."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO evaluation_metrics
                    (batch_id, actions_evaluated, conversion_rate,
                     critic_rewrite_success_rate, drift_flagged,
                     diagnostics, created_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, NOW())
                """,
                metrics.batch_id,
                metrics.actions_evaluated,
                metrics.conversion_rate,
                metrics.critic_rewrite_success_rate,
                metrics.drift_flagged,
                json.dumps(metrics.diagnostics),
            )

    async def get_recent_metrics(self, limit: int = 10) -> list[dict]:
        """Retrieve recent evaluation metrics for monitoring dashboards."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM evaluation_metrics
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(r) for r in rows]

    async def close(self) -> None:
        """Close the evaluator's connection pools."""
        global _evaluator
        if self._pool:
            await self._pool.close()
            self._pool = None
        if self._read_pool:
            await self._read_pool.close()
            self._read_pool = None
        _evaluator = None
        logger.info("EvaluatorAgent closed")


def get_evaluator() -> EvaluatorAgent:
    """Get the singleton EvaluatorAgent instance."""
    global _evaluator
    if _evaluator is None:
        _evaluator = EvaluatorAgent()
    return _evaluator


async def close_evaluator() -> None:
    """Close the singleton evaluator."""
    global _evaluator
    if _evaluator:
        await _evaluator.close()
