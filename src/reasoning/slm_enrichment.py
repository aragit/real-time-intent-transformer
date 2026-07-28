"""
SLM Enrichment Module (Phase 2)
================================
Neuro-symbolic enrichment layer backed by a local vLLM server.

Uses constrained decoding (response_format=json_object) to guarantee
structured output from the SLM for downstream rule-based processing.

NOT on the hot path. Falls back silently to keyword heuristics if the
vLLM server is unreachable or returns malformed output.
"""

import json
import time

from loguru import logger
from openai import AsyncOpenAI

from src.config import settings

# Lazy-initialized client
_client: AsyncOpenAI | None = None
# Simple in-memory cache: query -> (result, timestamp)
_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_client() -> AsyncOpenAI:
    """Get or create the async OpenAI client pointing at local vLLM."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.vllm_base_url,
            api_key=settings.vllm_api_key,
            timeout=settings.vllm_timeout,
        )
    return _client


class SLMEnrichment:
    """
    Local SLM enrichment for search query understanding and intent signals.

    Backed by Gemma 3n via vLLM's OpenAI-compatible API.
    Uses constrained decoding (json_object) for guaranteed structured output.
    """

    def __init__(self):
        self._available: bool | None = None  # None = unchecked

    async def health_check(self) -> bool:
        """Check if the vLLM server is reachable."""
        try:
            client = _get_client()
            models = await client.models.list()
            self._available = len(models.data) > 0
            return self._available
        except Exception as e:
            logger.debug(f"vLLM health check failed: {e}")
            self._available = False
            return False

    @property
    def available(self) -> bool:
        """Check if SLM has been confirmed available (no network call)."""
        return self._available is True

    async def enrich_search_query(self, query: str) -> dict[str, bool] | None:
        """
        Extract behavioral signals from raw search text via the SLM.

        Returns dict with keys: price_sensitive, brand_loyal,
        comparison_shopping, urgency. Returns None if SLM unavailable
        or output cannot be parsed.
        """
        if not query or not query.strip():
            return self._empty_signals()

        # Check cache
        cached = _cache.get(query)
        if cached and (time.monotonic() - cached[1]) < _CACHE_TTL_SECONDS:
            return cached[0]

        try:
            client = _get_client()
            response = await client.chat.completions.create(
                model=settings.vllm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a real-time intent classification engine. "
                            "Analyze the user's search query and output strictly "
                            "as a JSON object with boolean fields: "
                            '{"price_sensitive": bool, "brand_loyal": bool, '
                            '"comparison_shopping": bool, "urgency": bool}. '
                            "No other text."
                        ),
                    },
                    {"role": "user", "content": f"Search query: {query}"},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            result = json.loads(content)

            # Validate all expected keys are present and boolean
            signals = {
                "price_sensitive": bool(result.get("price_sensitive", False)),
                "brand_loyal": bool(result.get("brand_loyal", False)),
                "comparison_shopping": bool(result.get("comparison_shopping", False)),
                "urgency": bool(result.get("urgency", False)),
            }

            # Cache the result
            _cache[query] = (signals, time.monotonic())

            return signals

        except TimeoutError:
            logger.debug(f"SLM enrichment timeout for query: {query[:50]}")
            return None
        except Exception as e:
            logger.debug(f"SLM enrichment failed: {e}")
            return None

    async def enrich_intent(
        self,
        session_features: dict,
    ) -> dict | None:
        """
        Enrich session features with SLM-generated intent analysis.

        Returns dict with keys: intent, reasoning, confidence.
        Returns None if SLM unavailable or output cannot be parsed.
        """
        if not session_features:
            return None

        try:
            client = _get_client()
            response = await client.chat.completions.create(
                model=settings.vllm_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a real-time intent classification engine "
                            "for e-commerce sessions. Analyze the session features "
                            "and output strictly as a JSON object with keys: "
                            "intent (one of BROWSING, CARTING, CHECKOUT_INTENT, "
                            "PRODUCT_RETURN), reasoning (one sentence), "
                            "confidence (float 0.0-1.0). No other text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Session features: {json.dumps(session_features)}",
                    },
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            if not content:
                return None

            result = json.loads(content)

            return {
                "intent": str(result.get("intent", "BROWSING")),
                "reasoning": str(result.get("reasoning", "")),
                "confidence": float(result.get("confidence", 0.0)),
            }

        except TimeoutError:
            logger.debug("SLM intent enrichment timeout")
            return None
        except Exception as e:
            logger.debug(f"SLM intent enrichment failed: {e}")
            return None

    def enrich_fallback(self, query: str) -> dict[str, bool]:
        """Keyword-based fallback when SLM is down."""
        query_lower = query.lower()
        return {
            "price_sensitive": any(
                w in query_lower for w in ["cheap", "discount", "sale", "deal", "price"]
            ),
            "brand_loyal": any(
                w in query_lower for w in ["nike", "adidas", "apple", "sony"]
            ),
            "comparison_shopping": any(
                w in query_lower for w in ["best", "compare", "vs", "versus", "top"]
            ),
            "urgency": any(
                w in query_lower for w in ["now", "today", "urgent", "asap", "fast"]
            ),
        }

    @staticmethod
    def _empty_signals() -> dict[str, bool]:
        return {
            "price_sensitive": False,
            "brand_loyal": False,
            "comparison_shopping": False,
            "urgency": False,
        }


# Singleton
_slm: SLMEnrichment | None = None


def get_slm_enrichment() -> SLMEnrichment:
    """Get the singleton SLMEnrichment instance."""
    global _slm
    if _slm is None:
        _slm = SLMEnrichment()
    return _slm


async def close_slm() -> None:
    """Close the SLM enrichment client."""
    global _client, _slm
    if _client is not None:
        await _client.close()
        _client = None
    _slm = None
