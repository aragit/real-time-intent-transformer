from datetime import UTC, datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(UTC).isoformat(),
        version="0.1.0",
    )
