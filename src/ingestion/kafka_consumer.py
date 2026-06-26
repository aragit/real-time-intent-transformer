import json
from typing import Optional

from aiokafka import AIOKafkaConsumer
from loguru import logger

from src.config import settings
from src.models.events import ClickEvent


class ClickstreamConsumer:
    def __init__(self, bootstrap_servers: Optional[str] = None):
        self.bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._consumer: Optional[AIOKafkaConsumer] = None

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            settings.kafka_topic_clicks,
            bootstrap_servers=self.bootstrap_servers,
            group_id=settings.kafka_consumer_group,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        logger.info(f"Kafka consumer started: {self.bootstrap_servers}, group={settings.kafka_consumer_group}")

    async def stop(self):
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume(self, callback):
        if not self._consumer:
            raise RuntimeError("Consumer not started")
        async for msg in self._consumer:
            try:
                event = ClickEvent(**msg.value)
                await callback(event)
            except Exception as e:
                logger.error(f"Failed to process message: {e}")
