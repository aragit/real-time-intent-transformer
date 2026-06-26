from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.api.routes import actions, customers, events, health, intents, sessions
from src.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.app_name}")
    yield
    logger.info(f"Shutting down {settings.app_name}")


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
