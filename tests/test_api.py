import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from fastapi import status

from src.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

@pytest.mark.asyncio
async def test_root_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == status.HTTP_200_OK
        assert "real-time-intent-transformer" in response.json()["message"]

@pytest.mark.asyncio
async def test_get_features_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/sessions/nonexistent/features")
        assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_get_intent_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/sessions/nonexistent/intent")
        assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_get_markov_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/sessions/nonexistent/markov")
        assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_get_customer_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/customers/nonexistent/profile")
        assert response.status_code == status.HTTP_404_NOT_FOUND

@pytest.mark.asyncio
async def test_intents_distribution_stub():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/intents/distribution")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "distribution" in data
        assert "BROWSE" in data["distribution"]

@pytest.mark.asyncio
async def test_dispatch_action_minimal():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/actions/dispatch", params={"session_id": "s_dispatch", "intent": "BROWSE", "confidence": 0.8})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["action"] == "RECOMMEND_ALTERNATIVE"

@pytest.mark.asyncio
async def test_get_action_history_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/actions/s_fresh/history")
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []

@pytest.mark.asyncio
async def test_ingest_event_accepted():
    from datetime import datetime, timezone
    payload = {
        "session_id": "s_test",
        "customer_id": "c_test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": "page_view",
        "product_id": "p1",
        "category": "test",
        "value": None,
        "metadata": {},
    }
    with patch("src.api.routes.events._get_producer") as mock_get:
        mock_producer = AsyncMock()
        mock_get.return_value = mock_producer
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/events/ingest", json=payload)
            assert response.status_code == status.HTTP_202_ACCEPTED
            assert "event_id" in response.json()
            mock_producer.start.assert_called_once()
            mock_producer.send_event.assert_called_once()
            mock_producer.stop.assert_called_once()

@pytest.mark.asyncio
async def test_ingest_batch_accepted():
    from datetime import datetime, timezone
    payload = [
        {
            "session_id": "s_batch",
            "action": "page_view",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {},
        }
        for _ in range(5)
    ]
    with patch("src.api.routes.events._get_producer") as mock_get:
        mock_producer = AsyncMock()
        mock_get.return_value = mock_producer
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/events/ingest/batch", json=payload)
            assert response.status_code == status.HTTP_202_ACCEPTED
            assert response.json()["count"] == 5
            mock_producer.start.assert_called_once()
            mock_producer.send_batch.assert_called_once()
            mock_producer.stop.assert_called_once()
