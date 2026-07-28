"""
SLM Enrichment Tests
====================
Tests for the local SLM enrichment layer backed by vLLM.

All vLLM calls are fully mocked. Verifies:
  1. Search query enrichment (behavioral signal extraction)
  2. Intent enrichment (session feature analysis)
  3. Graceful degradation (timeout, malformed output, connection errors)
  4. Keyword-based fallback
  5. Caching behavior
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reasoning.slm_enrichment import SLMEnrichment, get_slm_enrichment

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(content: str) -> MagicMock:
    """Create a mock OpenAI chat completion response."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def _make_mock_client(response_content: str) -> MagicMock:
    """Create a mock AsyncOpenAI client that returns the given content."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_make_mock_response(response_content)
    )
    mock_client.models.list = AsyncMock(return_value=MagicMock(data=[MagicMock()]))
    mock_client.close = AsyncMock()
    return mock_client


# ---------------------------------------------------------------------------
# Search Query Enrichment
# ---------------------------------------------------------------------------


class TestEnrichSearchQuery:
    @pytest.mark.asyncio
    async def test_price_sensitive_query(self):
        """A query with 'cheap' and 'deal' should flag price_sensitive."""
        signals_json = json.dumps(
            {
                "price_sensitive": True,
                "brand_loyal": False,
                "comparison_shopping": False,
                "urgency": False,
            }
        )
        mock_client = _make_mock_client(signals_json)

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("cheap laptop deals")

        assert result["price_sensitive"] is True
        assert result["brand_loyal"] is False
        assert result["comparison_shopping"] is False
        assert result["urgency"] is False

    @pytest.mark.asyncio
    async def test_multi_signal_query(self):
        """A complex query should return multiple flags."""
        signals_json = json.dumps(
            {
                "price_sensitive": True,
                "brand_loyal": True,
                "comparison_shopping": True,
                "urgency": False,
            }
        )
        mock_client = _make_mock_client(signals_json)

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("best nike shoes vs adidas cheap sale")

        assert result["price_sensitive"] is True
        assert result["brand_loyal"] is True
        assert result["comparison_shopping"] is True
        assert result["urgency"] is False

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty_signals(self):
        """An empty query should return all-False signals without hitting the SLM."""
        slm = SLMEnrichment()
        slm._available = True
        result = await slm.enrich_search_query("")

        assert result is not None
        assert all(v is False for v in result.values())

    @pytest.mark.asyncio
    async def test_none_query_returns_empty_signals(self):
        """A None query should return all-False signals."""
        slm = SLMEnrichment()
        slm._available = True
        result = await slm.enrich_search_query(None)

        assert result is not None
        assert all(v is False for v in result.values())

    @pytest.mark.asyncio
    async def test_slm_returns_none_content(self):
        """If SLM returns empty content, should return None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(None)
        )

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_slm_timeout_returns_none(self):
        """Timeout should gracefully return None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=TimeoutError("timed out")
        )

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_slm_connection_error_returns_none(self):
        """Connection error should gracefully return None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=ConnectionError("vLLM unreachable")
        )

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_slm_malformed_json_returns_none(self):
        """Non-JSON output from SLM should return None."""
        mock_client = _make_mock_client("I cannot classify this query.")

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("test query")

        assert result is None

    @pytest.mark.asyncio
    async def test_slm_missing_keys_coerce_to_false(self):
        """Missing boolean keys should default to False."""
        signals_json = json.dumps({"price_sensitive": True})
        mock_client = _make_mock_client(signals_json)

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_search_query("cheap laptop")

        assert result["price_sensitive"] is True
        assert result["brand_loyal"] is False
        assert result["comparison_shopping"] is False
        assert result["urgency"] is False


# ---------------------------------------------------------------------------
# Intent Enrichment
# ---------------------------------------------------------------------------


class TestEnrichIntent:
    @pytest.mark.asyncio
    async def test_enrich_intent_returns_structured_output(self):
        """SLM should return intent, reasoning, confidence."""
        intent_json = json.dumps(
            {
                "intent": "CHECKOUT_INTENT",
                "reasoning": "High cart value with checkout actions detected",
                "confidence": 0.92,
            }
        )
        mock_client = _make_mock_client(intent_json)

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_intent(
                {"total_cart_value": 250.0, "cart_adds": 5, "checkouts": 1}
            )

        assert result["intent"] == "CHECKOUT_INTENT"
        assert result["confidence"] == 0.92
        assert "checkout" in result["reasoning"].lower()

    @pytest.mark.asyncio
    async def test_enrich_intent_empty_features_returns_none(self):
        """Empty features dict should return None."""
        slm = SLMEnrichment()
        slm._available = True
        result = await slm.enrich_intent({})

        assert result is None

    @pytest.mark.asyncio
    async def test_enrich_intent_timeout_returns_none(self):
        """Timeout should return None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=TimeoutError("timed out")
        )

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_intent({"total_cart_value": 100.0})

        assert result is None

    @pytest.mark.asyncio
    async def test_enrich_intent_malformed_json_returns_none(self):
        """Non-JSON output should return None."""
        mock_client = _make_mock_client("I don't understand these features.")

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True
            result = await slm.enrich_intent({"total_cart_value": 100.0})

        assert result is None


# ---------------------------------------------------------------------------
# Keyword Fallback
# ---------------------------------------------------------------------------


class TestEnrichFallback:
    def test_price_sensitive_keywords(self):
        slm = SLMEnrichment()
        result = slm.enrich_fallback("cheap laptop deals sale")
        assert result["price_sensitive"] is True

    def test_brand_loyal_keywords(self):
        slm = SLMEnrichment()
        result = slm.enrich_fallback("nike running shoes")
        assert result["brand_loyal"] is True

    def test_comparison_keywords(self):
        slm = SLMEnrichment()
        result = slm.enrich_fallback("best laptop compare vs macbook")
        assert result["comparison_shopping"] is True

    def test_urgency_keywords(self):
        slm = SLMEnrichment()
        result = slm.enrich_fallback("need it now today asap")
        assert result["urgency"] is True

    def test_no_signals(self):
        slm = SLMEnrichment()
        result = slm.enrich_fallback("shirt")
        assert all(v is False for v in result.values())


# ---------------------------------------------------------------------------
# Health Check & Availability
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        mock_client = _make_mock_client("{}")

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            result = await slm.health_check()

        assert result is True
        assert slm.available is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        mock_client = MagicMock()
        mock_client.models.list = AsyncMock(side_effect=ConnectionError("refused"))

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            result = await slm.health_check()

        assert result is False
        assert slm.available is False


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


class TestCaching:
    @pytest.mark.asyncio
    async def test_same_query_returns_cached_result(self):
        """Second call for same query should not hit the LLM."""
        import src.reasoning.slm_enrichment as mod

        mod._cache.clear()

        signals_json = json.dumps(
            {
                "price_sensitive": True,
                "brand_loyal": False,
                "comparison_shopping": False,
                "urgency": False,
            }
        )
        mock_client = _make_mock_client(signals_json)

        with patch("src.reasoning.slm_enrichment._get_client", return_value=mock_client):
            slm = SLMEnrichment()
            slm._available = True

            result1 = await slm.enrich_search_query("cheap laptop cache test")
            result2 = await slm.enrich_search_query("cheap laptop cache test")

        assert result1 == result2
        # Client should only be called once (second hit is from cache)
        mock_client.chat.completions.create.assert_called_once()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_slm_enrichment_returns_same_instance(self):

        # Reset singleton
        import src.reasoning.slm_enrichment as mod

        mod._slm = None

        slm1 = get_slm_enrichment()
        slm2 = get_slm_enrichment()
        assert slm1 is slm2
