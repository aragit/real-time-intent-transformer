from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

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
    with (
        patch("src.pipeline._get_classifier") as mock_cls,
        patch("src.pipeline._run_governance", new_callable=AsyncMock) as mock_gov,
    ):
        mock_classifier = MagicMock()
        mock_classifier.classify.return_value = ("BROWSE", 0.85, "rule_based")
        mock_cls.return_value = mock_classifier
        mock_gov.return_value = (True, "")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/actions/dispatch",
                params={"session_id": "s_dispatch", "intent": "BROWSE", "confidence": 0.8},
            )
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
    from datetime import datetime

    payload = {
        "session_id": "s_test",
        "customer_id": "c_test",
        "timestamp": datetime.now(UTC).isoformat(),
        "action": "page_view",
        "product_id": "p1",
        "category": "test",
        "value": None,
        "metadata": {},
    }
    with patch("src.api.routes.events.ingest_event", new_callable=AsyncMock) as mock_ingest:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/events/ingest", json=payload)
            assert response.status_code == status.HTTP_202_ACCEPTED
            assert "event_id" in response.json()
            mock_ingest.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_batch_accepted():
    from datetime import datetime

    payload = [
        {
            "session_id": "s_batch",
            "action": "page_view",
            "timestamp": datetime.now(UTC).isoformat(),
            "metadata": {},
        }
        for _ in range(5)
    ]
    with patch("src.api.routes.events.ingest_event", new_callable=AsyncMock) as mock_ingest:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/events/ingest/batch", json=payload)
            assert response.status_code == status.HTTP_202_ACCEPTED
            assert response.json()["count"] == 5
            assert mock_ingest.call_count == 5
