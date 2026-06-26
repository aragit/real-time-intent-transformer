import json
from typing import List, Optional

from aiokafka import AIOKafkaProducer
from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class ClickstreamProducer:
    def __init__(self, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
        )
        await self._producer.start()
        logger.info(f"Kafka producer started: {self.bootstrap_servers}")

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("Kafka producer stopped")

    async def send_event(self, event: ClickEvent) -> None:
        if not self._producer:
            raise RuntimeError("Producer not started")
        await self._producer.send(
            settings.kafka_topic_clicks,
            value=event.model_dump(),
        )
        logger.debug(f"Sent event {event.event_id} to {settings.kafka_topic_clicks}")

    async def send_batch(self, events: List[ClickEvent]) -> None:
        for event in events:
            await self.send_event(event)
        logger.info(f"Sent batch of {len(events)} events")
