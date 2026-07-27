"""
Run the Kafka consumer as a standalone module.

Usage:
    python -m src.ingestion.kafka_consumer
"""

import asyncio
import signal

from loguru import logger

from src.ingestion.kafka_consumer import ClickstreamConsumer


async def main() -> None:
    consumer = ClickstreamConsumer()

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _request_shutdown():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _request_shutdown)

    await consumer.start()

    run_task = asyncio.create_task(consumer.run())
    await shutdown_event.wait()

    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    await close_resources()
    logger.info("Consumer exited cleanly")


async def close_resources() -> None:
    from src.pipeline import close_pipeline

    await close_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
