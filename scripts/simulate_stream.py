#!/usr/bin/env python3
"""
Firehose Simulator
==================
Generates a rapid stream of synthetic e-commerce events and pushes
them to the Kafka retail topic. Simulates 3 concurrent browsing
sessions with realistic action sequences.

Usage:
    python scripts/simulate_stream.py
"""

import asyncio
import json
import os
import random
import time
import uuid
from datetime import UTC, datetime

from aiokafka import AIOKafkaProducer
from loguru import logger

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "ecommerce.clicks.raw")

SESSION_IDS = [f"sess_{uuid.uuid4().hex[:8]}" for _ in range(3)]
CUSTOMER_IDS = [f"cust_{uuid.uuid4().hex[:6]}" for _ in range(3)]

CATEGORIES = ["electronics", "clothing", "home", "sports", "books"]
PRODUCTS = {
    "electronics": ["prod_laptop_01", "prod_phone_01", "prod_headphones_01"],
    "clothing": ["prod_shirt_01", "prod_pants_01", "prod_shoes_01"],
    "home": ["prod_lamp_01", "prod_chair_01", "prod_table_01"],
    "sports": ["prod_yoga_01", "prod_dumbbell_01", "prod_bike_01"],
    "books": ["prod_novel_01", "prod_textbook_01", "prod_comic_01"],
}

ACTION_SEQUENCES = [
    # Session type A: Browser → Compare → Cart → Checkout
    [
        ("page_view", None, None, None),
        ("page_view", "electronics", None, None),
        ("search_query", "electronics", None, None),
        ("page_view", "electronics", 299.99, '{"query": "laptop deals"}'),
        ("filter_apply", "electronics", None, '{"filter": "price_low_to_high"}'),
        ("page_view", "electronics", 299.99, None),
        ("add_to_cart", "electronics", 299.99, None),
        ("page_view", "clothing", 49.99, None),
        ("add_to_cart", "clothing", 49.99, None),
        ("checkout_start", None, 349.98, None),
        ("purchase_complete", None, 349.98, '{"payment": "credit_card"}'),
        ("page_view", "books", 14.99, None),
    ],
    # Session type B: Searcher with urgency
    [
        ("page_view", "sports", None, None),
        ("search_query", "sports", None, '{"query": "running shoes nike"}'),
        ("page_view", "sports", 129.99, None),
        ("page_view", "sports", 119.99, None),
        ("page_view", "sports", 139.99, None),
        ("search_query", "sports", None, '{"query": "nike vs adidas comparison"}'),
        ("add_to_cart", "sports", 129.99, None),
        ("remove_from_cart", "sports", 129.99, None),
        ("add_to_cart", "sports", 119.99, None),
        ("page_view", "sports", 119.99, None),
        ("add_to_cart", "sports", 119.99, None),
        ("search_query", "sports", None, '{"query": "best deal running shoes asap"}'),
        ("page_view", "electronics", 599.99, None),
    ],
    # Session type C: Window shopper (high churn)
    [
        ("page_view", "clothing", None, None),
        ("page_view", "clothing", 89.99, None),
        ("page_view", "electronics", 199.99, None),
        ("search_query", "electronics", None, '{"query": "cheap laptop"}'),
        ("page_view", "electronics", 149.99, None),
        ("page_view", "home", 79.99, None),
        ("page_view", "books", 24.99, None),
        ("page_view", "sports", 59.99, None),
        ("search_query", "sports", None, '{"query": "yoga mat"}'),
        ("page_view", "home", 39.99, None),
        ("page_view", "clothing", 29.99, None),
        ("page_view", "electronics", 399.99, None),
        ("search_query", "electronics", None, '{"query": "phone deals today"}'),
        ("add_to_cart", "electronics", 399.99, None),
        ("remove_from_cart", "electronics", 399.99, None),
        ("page_view", "clothing", 59.99, None),
    ],
]


def _build_event(
    session_id: str,
    customer_id: str,
    action: str,
    category: str | None,
    value: float | None,
    metadata_json: str | None,
    offset_ms: int,
) -> dict:
    product_id = None
    if category and category in PRODUCTS:
        product_id = random.choice(PRODUCTS[category])

    metadata = {}
    if metadata_json:
        metadata = json.loads(metadata_json)

    return {
        "event_id": str(uuid.uuid4())[:12],
        "session_id": session_id,
        "customer_id": customer_id,
        "timestamp": (
            datetime.now(UTC).isoformat()
        ),
        "action": action,
        "product_id": product_id,
        "category": category,
        "value": value,
        "metadata": metadata,
    }


async def main() -> int:
    producer = AIOKafkaProducer(
        bootstrap_servers=BOOTSTRAP_SERVERS,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )
    await producer.start()
    print(f"Connected to {BOOTSTRAP_SERVERS}")
    print(f"Topic: {TOPIC}")
    print(f"Sessions: {SESSION_IDS}")
    print("=" * 70)

    total_events = 0
    start_time = time.monotonic()

    for i, (session_id, customer_id, actions) in enumerate(
        zip(SESSION_IDS, CUSTOMER_IDS, ACTION_SEQUENCES)
    ):
        print(f"\n--- Session {i + 1}: {session_id} ---")
        for j, (action, category, value, meta) in enumerate(actions):
            event = _build_event(
                session_id, customer_id, action, category, value, meta, j * 50
            )
            await producer.send_and_wait(TOPIC, value=event)
            total_events += 1

            value_str = f"${value:.2f}" if value else "-"
            meta_str = f" {meta}" if meta else ""
            print(
                f"  [{total_events:3d}] {action:<20s} "
                f"cat={category or 'none':<12s} "
                f"val={value_str:<10s}{meta_str}"
            )
            # Small random delay between events (1-10ms) for realism
            await asyncio.sleep(random.uniform(0.001, 0.010))

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 70)
    print(f"Done. {total_events} events in {elapsed:.2f}s ({total_events / elapsed:.0f} events/sec)")

    await producer.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
