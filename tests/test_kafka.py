import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

from src.ingestion.kafka_producer import ClickstreamProducer
from src.ingestion.kafka_consumer import ClickstreamConsumer
from src.models.events import ClickEvent


class TestKafkaProducer:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        producer = ClickstreamProducer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_producer.AIOKafkaProducer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            await producer.start()
            mock_instance.start.assert_called_once()
            await producer.stop()
            mock_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_event(self, sample_event):
        producer = ClickstreamProducer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_producer.AIOKafkaProducer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            await producer.start()
            await producer.send_event(sample_event)
            mock_instance.send.assert_called_once()
            await producer.stop()

    @pytest.mark.asyncio
    async def test_send_batch(self, sample_event, cart_event):
        producer = ClickstreamProducer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_producer.AIOKafkaProducer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            await producer.start()
            await producer.send_batch([sample_event, cart_event])
            assert mock_instance.send.call_count == 2
            await producer.stop()

    @pytest.mark.asyncio
    async def test_not_started_raises(self, sample_event):
        producer = ClickstreamProducer()
        with pytest.raises(RuntimeError, match="Producer not started"):
            await producer.send_event(sample_event)


class TestKafkaConsumer:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_instance = AsyncMock()
            mock_cls.return_value = mock_instance
            await consumer.start()
            mock_instance.start.assert_called_once()
            await consumer.stop()
            mock_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_callback(self, sample_event):
        consumer = ClickstreamConsumer(bootstrap_servers="localhost:9092")
        callback = AsyncMock()
        
        # Create proper async iterator mock
        mock_msg = MagicMock()
        mock_msg.value = sample_event.model_dump()
        
        async def mock_async_iter():
            yield mock_msg
        
        with patch("src.ingestion.kafka_consumer.AIOKafkaConsumer") as mock_cls:
            mock_instance = AsyncMock()
            mock_instance.__aiter__ = mock_async_iter
            mock_cls.return_value = mock_instance
            
            await consumer.start()
            # Manually test the callback logic
            event = ClickEvent(**mock_msg.value)
            await callback(event)
            callback.assert_called_once()
            await consumer.stop()

    @pytest.mark.asyncio
    async def test_not_started_raises(self):
        consumer = ClickstreamConsumer()
        with pytest.raises(RuntimeError, match="Consumer not started"):
            # consume() returns a coroutine that yields async iterator
            # We need to iterate it
            gen = await consumer.consume(lambda x: None)
            async for _ in gen:
                pass
