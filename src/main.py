import os
from dotenv import load_dotenv

load_dotenv()

# Explicitly export Langfuse keys so @observe decorators see them at import time
if os.getenv("LANGFUSE_PUBLIC_KEY"):
    os.environ["LANGFUSE_PUBLIC_KEY"] = os.getenv("LANGFUSE_PUBLIC_KEY")
if os.getenv("LANGFUSE_SECRET_KEY"):
    os.environ["LANGFUSE_SECRET_KEY"] = os.getenv("LANGFUSE_SECRET_KEY")
if os.getenv("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = os.getenv("LANGFUSE_HOST")

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.api.routes import actions, customers, events, health, intents, sessions
from src.config import settings

_evaluator_task: asyncio.Task | None = None
_kafka_consumer = None


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from src.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY

        start = time.time()
        response = await call_next(request)
        duration = time.time() - start

        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code,
        ).inc()
        REQUEST_LATENCY.observe(duration)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _evaluator_task, _kafka_consumer
    logger.info(f"Starting {settings.app_name}")

    # Start Kafka consumer
    try:
        from src.ingestion.kafka_consumer import ClickstreamConsumer

        _kafka_consumer = ClickstreamConsumer()
        await _kafka_consumer.start()
        logger.info("Kafka consumer started")
    except Exception as e:
        logger.warning(f"Could not start Kafka consumer: {e}")

    # Start the evaluator background worker
    try:
        from src.workers.evaluator_worker import start_evaluator_loop

        _evaluator_task = asyncio.create_task(
            start_evaluator_loop(interval_seconds=300, batch_size=100)
        )
        logger.info("Evaluator background worker started")
    except Exception as e:
        logger.warning(f"Could not start evaluator worker: {e}")

    yield

    logger.info(f"Shutting down {settings.app_name}")

    # Stop Kafka consumer
    if _kafka_consumer:
        try:
            await _kafka_consumer.stop()
        except Exception as e:
            logger.warning(f"Error stopping Kafka consumer: {e}")

    # Cancel the evaluator worker
    if _evaluator_task and not _evaluator_task.done():
        _evaluator_task.cancel()
        try:
            await _evaluator_task
        except asyncio.CancelledError:
            pass

    # Clean up evaluator resources
    try:
        from src.workers.evaluator_worker import stop_evaluator_worker

        await stop_evaluator_worker()
    except Exception as e:
        logger.warning(f"Error stopping evaluator worker: {e}")

    from src.pipeline import close_pipeline

    await close_pipeline()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(MetricsMiddleware)

app.include_router(health.router, tags=["health"])
app.include_router(events.router, tags=["events"])
app.include_router(sessions.router, tags=["sessions"])
app.include_router(actions.router, tags=["actions"])
app.include_router(customers.router, tags=["customers"])
app.include_router(intents.router, tags=["intents"])


@app.get("/")
async def root():
    return {"message": settings.app_name}
