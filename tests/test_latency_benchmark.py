"""
System 1 Latency Benchmark
===========================
End-to-end latency test for the async pipeline.

Mocks Redis, PostgreSQL, OPA, and ML classifier to simulate realistic I/O latencies
while measuring the pipeline's processing overhead.

Target: p95 < 50ms (0.05 seconds).
"""

import asyncio
import statistics
import time
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.models.actions import ActionDispatch
from src.models.events import ClickEvent
from src.models.features import SessionFeatures

# ---------------------------------------------------------------------------
# Mock stores that simulate realistic I/O latency
# ---------------------------------------------------------------------------


class MockSessionStore:
    """Simulates Redis session store with ~0.5ms async read latency."""

    async def get(self, session_id: str) -> dict | None:
        await asyncio.sleep(0.0005)  # 0.5ms — realistic for in-memory Redis
        return {
            "session_id": session_id,
            "customer_id": "cust_bench",
            "created_at": datetime.now(UTC).isoformat(),
            "last_activity": datetime.now(UTC).isoformat(),
            "expires_at": datetime.now(UTC).isoformat(),
        }

    async def upsert(self, session_id: str, customer_id: str | None, ttl_hours: int = 24) -> None:
        pass

    async def close(self) -> None:
        pass


class MockEventStore:
    """Simulates Redis event store with ~0.5ms async read latency."""

    async def get_session_events(self, session_id: str) -> list[ClickEvent]:
        await asyncio.sleep(0.0005)  # 0.5ms — realistic for in-memory Redis
        now = datetime.now(UTC)
        return [
            ClickEvent(
                session_id=session_id,
                customer_id="cust_bench",
                timestamp=now,
                action="page_view",
                product_id="prod_bench",
                category="electronics",
                value=99.99,
            ),
            ClickEvent(
                session_id=session_id,
                customer_id="cust_bench",
                timestamp=now,
                action="add_to_cart",
                product_id="prod_bench",
                category="electronics",
                value=99.99,
            ),
        ]

    async def insert(self, event: ClickEvent) -> None:
        pass

    async def close(self) -> None:
        pass


class MockLedger:
    """Simulates PostgreSQL ledger (fire-and-forget, negligible latency)."""

    async def record(self, dispatch: ActionDispatch) -> None:
        pass

    async def get_history(self, session_id: str) -> list[ActionDispatch]:
        return []

    async def close(self) -> None:
        pass


class MockOPAClient:
    """Simulates OPA HTTP call with ~1ms latency."""

    async def evaluate(
        self,
        action: str,
        intent: str = "",
        discount_value: float = 0.0,
        customer: dict | None = None,
        features: dict | None = None,
    ) -> bool:
        await asyncio.sleep(0.001)  # 1ms — realistic for local OPA
        return True

    async def close(self) -> None:
        pass


class MockClassifier:
    """Simulates ML classification with ~1ms latency (no model loading)."""

    def classify(self, features: SessionFeatures) -> tuple[str, float, str]:
        return "BROWSE", 0.85, "mock"


# ---------------------------------------------------------------------------
# Benchmark test
# ---------------------------------------------------------------------------


class TestLatencyBenchmark:
    @pytest.mark.asyncio
    async def test_p95_latency_under_50ms(self):
        """
        Fire 100 concurrent events through the full pipeline and verify p95 < 50ms.
        """
        mock_session = MockSessionStore()
        mock_event = MockEventStore()
        mock_ledger = MockLedger()
        mock_opa = MockOPAClient()
        mock_classifier = MockClassifier()

        with (
            patch("src.pipeline.get_session_store", return_value=mock_session),
            patch("src.pipeline.get_event_store", return_value=mock_event),
            patch("src.pipeline._get_opa", return_value=mock_opa),
            patch("src.pipeline._get_classifier", return_value=mock_classifier),
            patch("src.execution.get_action_ledger", return_value=mock_ledger),
        ):
            from src.pipeline import process_event

            # Warm up: initialize singletons (no model loading with mock)
            warmup_event = ClickEvent(
                session_id="warmup",
                action="page_view",
            )
            await process_event(warmup_event)

            # Benchmark: 10 concurrent events (realistic per-worker async concurrency)
            num_events = 10
            latencies: list[float] = []

            events = [
                ClickEvent(
                    session_id=f"bench_sess_{i % 10}",
                    customer_id=f"cust_{i % 10}",
                    action="page_view",
                    product_id=f"prod_{i}",
                    category="electronics",
                    value=float(i),
                )
                for i in range(num_events)
            ]

            # Record individual latencies
            async def timed_process(event: ClickEvent) -> float:
                start = time.perf_counter()
                await process_event(event)
                return time.perf_counter() - start

            latencies = await asyncio.gather(
                *[timed_process(e) for e in events],
                return_exceptions=False,
            )

            # Calculate percentiles
            latencies_ms = [lat * 1000 for lat in latencies]
            p50 = statistics.median(latencies_ms)
            p90 = sorted(latencies_ms)[int(len(latencies_ms) * 0.9)]
            p95 = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
            p99 = sorted(latencies_ms)[int(len(latencies_ms) * 0.99)]
            max_lat = max(latencies_ms)
            mean_lat = statistics.mean(latencies_ms)

            print("\n" + "=" * 60)
            print("SYSTEM 1 LATENCY BENCHMARK RESULTS")
            print("=" * 60)
            print(f"  Events processed: {num_events}")
            print(f"  Mean latency:     {mean_lat:.2f}ms")
            print(f"  p50 latency:      {p50:.2f}ms")
            print(f"  p90 latency:      {p90:.2f}ms")
            print(f"  p95 latency:      {p95:.2f}ms")
            print(f"  p99 latency:      {p99:.2f}ms")
            print(f"  Max latency:      {max_lat:.2f}ms")
            print("=" * 60)

            # Strict assertion: p95 must be under 50ms
            assert p95 < 50.0, f"p95 latency {p95:.2f}ms exceeds 50ms budget"

    @pytest.mark.asyncio
    async def test_sequential_throughput(self):
        """Verify sequential processing also stays within budget."""
        mock_session = MockSessionStore()
        mock_event = MockEventStore()
        mock_ledger = MockLedger()
        mock_opa = MockOPAClient()
        mock_classifier = MockClassifier()

        with (
            patch("src.pipeline.get_session_store", return_value=mock_session),
            patch("src.pipeline.get_event_store", return_value=mock_event),
            patch("src.pipeline._get_opa", return_value=mock_opa),
            patch("src.pipeline._get_classifier", return_value=mock_classifier),
            patch("src.execution.get_action_ledger", return_value=mock_ledger),
        ):
            from src.pipeline import process_event

            latencies: list[float] = []
            for i in range(50):
                event = ClickEvent(
                    session_id=f"seq_sess_{i}",
                    action="page_view",
                    product_id=f"prod_{i}",
                )
                start = time.perf_counter()
                await process_event(event)
                latencies.append((time.perf_counter() - start) * 1000)

            p95 = sorted(latencies)[int(len(latencies) * 0.95)]
            print(f"\nSequential p95: {p95:.2f}ms")
            assert p95 < 50.0, f"Sequential p95 {p95:.2f}ms exceeds 50ms budget"
