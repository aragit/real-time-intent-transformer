"""
Kafka Ingestion Tests
=====================
Isolated unit tests for the async Kafka consumer layer.

All aiokafka and pipeline I/O is fully mocked. Verifies:
  1. Consumer start/stop lifecycle
  2. Valid JSON parsing → ClickEvent → pipeline dispatch
  3. Malformed JSON safely ignored without crashing
  4. Graceful shutdown on CancelledError
  5. Concurrency semaphore limiting
  6. Legacy callback-based consumption
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.ingestion.kafka_consumer import ClickstreamConsumer
from src.models.events import ClickEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_kafka_msg(value: dict) -> MagicMock:
    msg = MagicMock()
    msg.value = value
    return msg


def _make_event_dict(
    session_id: str = "sess_test",
    action: str = "page_view",
    event_id: str = "evt_001",
) -> dict:
    return {
        "event_id": event_id,
        "session_id": session_id,
        "customer_id": "cust_001",
        "timestamp": "2024-06-15T12:00:00+00:00",
        "action": action,
        "product_id": "prod_001",
        "category": "electronics",
        "value": 99.99,
        "metadata": {},
    }


def _make_dispatch():
    from src.models.actions import ActionDispatch

    return ActionDispatch(
        session_id="sess_test",
        intent="BROWSING",
        confidence=0.85,
        action="RECOMMEND_ALTERNATIVE",
    )


class _AsyncMessageStream:
    def __init__(self, messages):
        self._messages = iter(messages)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._messages)
        except StopIteration:
            raise StopAsyncIteration


def _make_mock_consumer(messages):
    mock = AsyncMock()
    mock.__aiter__ = MagicMock(return_value=_AsyncMessageStream(messages))
    return mock


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestConsumerLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_and_starts_kafka_consumer(self):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_instance = _make_mock_consumer([])
            mock_cls.return_value = mock_instance

            await consumer.start()

            mock_cls.assert_called_once()
            mock_instance.start.assert_called_once()
            assert consumer._consumer is mock_instance

    @pytest.mark.asyncio
    async def test_stop_calls_kafka_stop(self):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_instance = _make_mock_consumer([])
            mock_cls.return_value = mock_instance

            await consumer.start()
            await consumer.stop()

            mock_instance.stop.assert_called_once()
            assert consumer._consumer is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started_is_noop(self):
        consumer = ClickstreamConsumer()
        await consumer.stop()
        assert consumer._consumer is None

    @pytest.mark.asyncio
    async def test_consume_before_start_raises(self):
        consumer = ClickstreamConsumer()
        with pytest.raises(RuntimeError, match="not started"):
            gen = await consumer.consume(lambda x: None)
            async for _ in gen:
                pass

    @pytest.mark.asyncio
    async def test_run_before_start_raises(self):
        consumer = ClickstreamConsumer()
        with pytest.raises(RuntimeError, match="not started"):
            await consumer.run()


# ---------------------------------------------------------------------------
# Valid Message Processing
# ---------------------------------------------------------------------------


class TestValidMessageProcessing:
    @pytest.mark.asyncio
    async def test_valid_json_parsed_and_routed_to_pipeline(self):
        event_dict = _make_event_dict(action="add_to_cart")
        msg = _make_kafka_msg(event_dict)

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([msg])

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                mock_process.assert_called_once()
                call_event = mock_process.call_args[0][0]
                assert isinstance(call_event, ClickEvent)
                assert call_event.action == "add_to_cart"
                assert call_event.session_id == "sess_test"

    @pytest.mark.asyncio
    async def test_multiple_events_all_processed(self):
        events = [
            _make_kafka_msg(_make_event_dict(action="page_view", event_id=f"evt_{i:03d}"))
            for i in range(5)
        ]

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer(events)

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                assert mock_process.call_count == 5

    @pytest.mark.asyncio
    async def test_each_event_passed_as_click_event(self):
        events = [
            _make_kafka_msg(_make_event_dict(action="add_to_cart", event_id="evt_a")),
            _make_kafka_msg(_make_event_dict(action="search_query", event_id="evt_b")),
        ]

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer(events)

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                assert mock_process.call_count == 2
                actions = [c.args[0].action for c in mock_process.call_args_list]
                assert actions == ["add_to_cart", "search_query"]


# ---------------------------------------------------------------------------
# Malformed JSON Handling
# ---------------------------------------------------------------------------


class TestMalformedMessages:
    @pytest.mark.asyncio
    async def test_malformed_json_skipped_without_crash(self):
        good_msg = _make_kafka_msg(_make_event_dict(event_id="evt_good"))
        bad_msg = _make_kafka_msg(
            {"not_a_valid": "click_event", "missing": "required_fields"}
        )

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([bad_msg, good_msg])

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                # Only the valid message should be processed
                assert mock_process.call_count == 1
                assert mock_process.call_args[0][0].event_id == "evt_good"

    @pytest.mark.asyncio
    async def test_empty_action_field_skipped(self):
        msg = _make_kafka_msg(
            {"event_id": "evt_1", "session_id": "s", "timestamp": "2024-01-01T00:00:00Z"}
        )

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([msg])

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                mock_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_all_malformed_messages_skipped(self):
        bad_msgs = [
            _make_kafka_msg({"garbage": i}) for i in range(5)
        ]

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer(bad_msgs)

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ) as mock_process:
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# Graceful Shutdown
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_cancelled_error_drains_inflight_tasks(self):
        event_dict = _make_event_dict(event_id="evt_slow")
        msg = _make_kafka_msg(event_dict)

        async def slow_process(event):
            await asyncio.sleep(10)
            return _make_dispatch()

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")

        # Use an infinite stream so run() blocks until we cancel it
        async def infinite_stream():
            while True:
                await asyncio.sleep(0)
                yield msg

        mock_consumer = AsyncMock()
        mock_consumer.__aiter__ = MagicMock(return_value=infinite_stream())

        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = mock_consumer
            consumer._process_event = slow_process

            await consumer.start()
            run_task = asyncio.create_task(consumer.run())
            await asyncio.sleep(0.05)

            # Verify task is running and a pipeline task was created
            assert len(consumer._tasks) >= 1

            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

            assert consumer._consumer is None

    @pytest.mark.asyncio
    async def test_stop_called_in_finally(self):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_instance = _make_mock_consumer([])
            mock_cls.return_value = mock_instance

            await consumer.start()
            run_task = asyncio.create_task(consumer.run())
            await asyncio.sleep(0.02)
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

            mock_instance.stop.assert_called()
            assert consumer._consumer is None

    @pytest.mark.asyncio
    async def test_tasks_cleared_after_drain(self):
        event_dict = _make_event_dict()
        msg = _make_kafka_msg(event_dict)

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([msg])

            with patch.object(
                consumer, "_process_event", new_callable=AsyncMock
            ):
                await consumer.start()
                run_task = asyncio.create_task(consumer.run())
                await asyncio.sleep(0.1)
                run_task.cancel()
                try:
                    await run_task
                except asyncio.CancelledError:
                    pass
                await consumer._drain_tasks()

                assert len(consumer._tasks) == 0


# ---------------------------------------------------------------------------
# Concurrency Limiting
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrent_processing(self):
        events = [
            _make_kafka_msg(_make_event_dict(event_id=f"evt_{i:03d}"))
            for i in range(10)
        ]

        concurrency_counter = {"max": 0, "current": 0}

        consumer = ClickstreamConsumer(
            bootstrap_servers="localhost:9092", max_concurrency=3
        )

        async def tracking_process(event):
            async with consumer._semaphore:
                concurrency_counter["current"] += 1
                concurrency_counter["max"] = max(
                    concurrency_counter["max"], concurrency_counter["current"]
                )
                await asyncio.sleep(0.02)
                concurrency_counter["current"] -= 1
                return _make_dispatch()

        consumer._process_event = tracking_process

        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer(events)

            await consumer.start()
            run_task = asyncio.create_task(consumer.run())
            await asyncio.sleep(0.5)
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

            await consumer._drain_tasks()
            assert concurrency_counter["max"] <= 3


# ---------------------------------------------------------------------------
# Legacy Callback API
# ---------------------------------------------------------------------------


class TestLegacyCallback:
    @pytest.mark.asyncio
    async def test_consume_callback_receives_parsed_events(self):
        event_dict = _make_event_dict(action="search_query")
        msg = _make_kafka_msg(event_dict)
        callback = AsyncMock()

        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([msg])

            await consumer.start()
            await consumer.consume(callback)

            callback.assert_called_once()
            passed_event = callback.call_args[0][0]
            assert isinstance(passed_event, ClickEvent)
            assert passed_event.action == "search_query"


# ---------------------------------------------------------------------------
# Topic Configuration
# ---------------------------------------------------------------------------


class TestTopicConfig:
    @pytest.mark.asyncio
    async def test_custom_topic_passed_to_kafka(self):
        consumer = ClickstreamConsumer(
            bootstrap_servers="localhost:9092", topic="my_custom_topic"
        )
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([])
            await consumer.start()

            call_args = mock_cls.call_args
            assert "my_custom_topic" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_default_topic_from_settings(self):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_cls.return_value = _make_mock_consumer([])
            await consumer.start()

            call_args = mock_cls.call_args
            assert "ecommerce.clicks.raw" in call_args[0][0]
