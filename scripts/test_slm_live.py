#!/usr/bin/env python3
"""
Live SLM Enrichment Test
========================
Connects to the local Ollama server and verifies the SLM enrichment pipeline.

Usage:
    python scripts/test_slm_live.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.reasoning.slm_enrichment import SLMEnrichment, close_slm


async def main():
    slm = SLMEnrichment()

    print("=" * 60)
    print("Live SLM Enrichment Test")
    print("=" * 60)

    # 1. Health check
    print("\n[1] Health check...")
    t0 = time.monotonic()
    healthy = await slm.health_check()
    elapsed = (time.monotonic() - t0) * 1000
    if healthy:
        print(f"    OK  vLLM reachable ({elapsed:.0f}ms)")
    else:
        print("    FAIL  vLLM unreachable — is Ollama running on :11434?")
        await close_slm()
        return 1

    # 2. Search query enrichment
    queries = [
        ("cheap laptop deals sale", {"price_sensitive": True}),
        ("best nike shoes vs adidas", {"brand_loyal": True, "comparison_shopping": True}),
        ("need it now asap", {"urgency": True}),
        ("just browsing some shirts", {}),
    ]

    print("\n[2] Search query enrichment:")
    for query, expected_signals in queries:
        t0 = time.monotonic()
        result = await slm.enrich_search_query(query)
        elapsed = (time.monotonic() - t0) * 1000

        if result is None:
            print(f"    FAIL  '{query[:40]}' -> None ({elapsed:.0f}ms)")
            continue

        # Check expected signals
        checks = []
        for signal, expected_val in expected_signals.items():
            actual = result.get(signal, False)
            status = "OK" if actual == expected_val else "WRONG"
            checks.append(status)
            if status == "WRONG":
                print(f"         {signal}: expected {expected_val}, got {actual}")

        verdict = "OK" if all(c == "OK" for c in checks) else "FAIL"
        flags = " ".join(f"{k}={v}" for k, v in result.items() if v)
        print(f"    {verdict}  '{query[:40]}' -> [{flags}] ({elapsed:.0f}ms)")

    # 3. Intent enrichment
    print("\n[3] Intent enrichment:")
    sessions = [
        {"total_cart_value": 250.0, "cart_adds": 5, "checkouts": 1},
        {"total_cart_value": 0.0, "cart_adds": 0, "checkouts": 0},
    ]
    for features in sessions:
        t0 = time.monotonic()
        result = await slm.enrich_intent(features)
        elapsed = (time.monotonic() - t0) * 1000

        if result is None:
            print(f"    FAIL  features={features} -> None ({elapsed:.0f}ms)")
            continue

        print(
            f"    OK    intent={result['intent']}  "
            f"conf={result['confidence']:.2f}  "
            f"reasoning={result['reasoning'][:50]}...  "
            f"({elapsed:.0f}ms)"
        )

    # 4. Caching
    print("\n[4] Caching (second call for same query):")
    q = "cache test cheap laptop"
    await slm.enrich_search_query(q)  # prime cache
    t0 = time.monotonic()
    await slm.enrich_search_query(q)  # should be cached
    elapsed = (time.monotonic() - t0) * 1000
    print(f"    OK    cached call: {elapsed:.1f}ms")

    # 5. Fallback (no SLM needed)
    print("\n[5] Keyword fallback:")
    fallback = slm.enrich_fallback("cheap nike shoes vs adidas best deal now")
    flags = " ".join(f"{k}={v}" for k, v in fallback.items() if v)
    print(f"    OK    [{flags}]")

    await close_slm()
    print("\n" + "=" * 60)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
