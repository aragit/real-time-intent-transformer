from fastapi import APIRouter, status
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


@router.get("/health", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="0.1.0",
    )
