"""
Kafka Ingestion Layer
=====================
Asynchronous consumer backed by aiokafka. Reads from the retail topic,
deserializes JSON payloads into ClickEvent models, and feeds them into
the hot-path pipeline (ingest → feature-engineer → classify → govern → dispatch).

All I/O is non-blocking. A bounded semaphore caps concurrency to prevent
OOM under burst traffic. Graceful shutdown drains in-flight work.
"""

import asyncio
import json

from aiokafka import AIOKafkaConsumer
from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class ClickstreamConsumer:
    """Async Kafka consumer that bridges the event stream to the processing pipeline."""

    def __init__(
        self,
        bootstrap_servers: str | None = None,
        topic: str | None = None,
        max_concurrency: int = 50,
    ):
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self.topic = topic or settings.kafka_topic_clicks
        self._consumer: AIOKafkaConsumer | None = None
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._tasks: set[asyncio.Task] = set()

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            self.topic,
            bootstrap_servers=self.bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        logger.info(
            f"Kafka consumer started: {self.bootstrap_servers} "
            f"topic={self.topic} group={settings.kafka_consumer_group}"
        )

    async def stop(self):
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Kafka consumer stopped")

    async def _process_event(self, event: ClickEvent) -> None:
        """Ingest and process a single event through the full pipeline."""
        async with self._semaphore:
            try:
                from src.pipeline import ingest_event, process_event

                await ingest_event(event)
                dispatch = await process_event(event)
                logger.info(
                    f"Processed event {event.event_id} "
                    f"session={event.session_id} "
                    f"action={dispatch.action} "
                    f"intent={dispatch.intent} "
                    f"confidence={dispatch.confidence:.2f}"
                )
            except Exception as e:
                logger.error(
                    f"Pipeline failed for event {event.event_id}: {e}"
                )

    async def _drain_tasks(self, timeout: float = 2.0) -> None:
        """Wait for in-flight tasks to finish, then cancel stragglers."""
        if not self._tasks:
            return
        logger.info(f"Draining {len(self._tasks)} in-flight tasks...")
        _, pending = await asyncio.wait(self._tasks, timeout=timeout)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._tasks.clear()

    def _on_task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc and not isinstance(exc, asyncio.CancelledError):
            logger.error(f"Background task failed: {exc}")

    async def consume(self, callback):
        """Legacy callback-based consumption. Yields ClickEvent objects."""
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        async for msg in self._consumer:
            try:
                event = ClickEvent(**msg.value)
                await callback(event)
            except Exception as e:
                logger.error(f"Failed to process message: {e}")

    async def run(self) -> None:
        """
        Main consumer loop. Reads events, dispatches to the pipeline,
        and handles graceful shutdown on CancelledError.
        """
        if not self._consumer:
            raise RuntimeError("Consumer not started. Call start() first.")

        logger.info("Consumer run loop started, waiting for events...")
        try:
            async for msg in self._consumer:
                try:
                    event = ClickEvent(**msg.value)
                except Exception as e:
                    logger.warning(f"Malformed message, skipping: {e}")
                    continue

                task = asyncio.create_task(self._process_event(event))
                self._tasks.add(task)
                task.add_done_callback(self._on_task_done)

        except asyncio.CancelledError:
            logger.info("Consumer run loop cancelled, shutting down...")
        finally:
            try:
                await self._drain_tasks()
            except asyncio.CancelledError:
                pass
            await self.stop()
