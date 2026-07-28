"""
Run the Kafka consumer as a standalone module.

Usage:
    python -m src.ingestion.kafka_consumer
"""

import asyncio
import signal
import traceback

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

    try:
        await consumer.start()
    except Exception:
        logger.error(
            f"Consumer failed to start:\n{traceback.format_exc()}"
        )
        return

    run_task = asyncio.create_task(consumer.run())
    try:
        await shutdown_event.wait()
    except Exception:
        logger.error(
            f"Shutdown wait interrupted:\n{traceback.format_exc()}"
        )

    run_task.cancel()
    try:
        await run_task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.error(
            f"Run task raised during cancellation:\n{traceback.format_exc()}"
        )

    try:
        await close_resources()
    except Exception:
        logger.error(
            f"Error closing resources:\n{traceback.format_exc()}"
        )

    logger.info("Consumer exited cleanly")


async def close_resources() -> None:
    from src.pipeline import close_pipeline

    await close_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
