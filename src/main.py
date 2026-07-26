import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.api.routes import actions, customers, events, health, intents, sessions
from src.config import settings

_evaluator_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _evaluator_task
    logger.info(f"Starting {settings.app_name}")

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

app.include_router(health.router, tags=["health"])
app.include_router(events.router, tags=["events"])
app.include_router(sessions.router, tags=["sessions"])
app.include_router(actions.router, tags=["actions"])
app.include_router(customers.router, tags=["customers"])
app.include_router(intents.router, tags=["intents"])


@app.get("/")
async def root():
    return {"message": settings.app_name}
