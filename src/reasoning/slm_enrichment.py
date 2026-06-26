from typing import Dict, Optional

from loguru import logger


class SLMEnrichment:
    """
    Phase 2: Ollama gemma3:1b enrichment for search query understanding.
    NOT on the hot path. Falls back silently if Ollama unavailable.
    """

    def __init__(self, model: str = "gemma3:1b", ollama_url: str = "http://localhost:11434"):
        self.model = model
        self.ollama_url = ollama_url
        self.available = False  # Stub: set True when Ollama confirmed running

    async def enrich_search_query(self, query: str) -> Optional[Dict[str, bool]]:
        """
        Extract behavioral signals from raw search text.
        Returns dict with keys: price_sensitive, brand_loyal, comparison_shopping, urgency
        """
        if not self.available:
            logger.debug("SLM enrichment skipped: Ollama not available")
            return None

        # Phase 2 implementation:
        # 1. POST to Ollama /api/generate with structured prompt
        # 2. Parse JSON response for boolean flags
        # 3. Cache result per query for 1 hour
        return None

    def enrich_fallback(self, query: str) -> Dict[str, bool]:
        """Keyword-based fallback when SLM is down."""
        query_lower = query.lower()
        return {
            "price_sensitive": any(w in query_lower for w in ["cheap", "discount", "sale", "deal", "price"]),
            "brand_loyal": any(w in query_lower for w in ["nike", "adidas", "apple", "sony"]),
            "comparison_shopping": any(w in query_lower for w in ["best", "compare", "vs", "versus", "top"]),
            "urgency": any(w in query_lower for w in ["now", "today", "urgent", "asap", "fast"]),
        }
