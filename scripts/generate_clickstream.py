#!/usr/bin/env python3
"""
Generate synthetic labeled clickstream data for training the intent classifier.
"""

import json
import os
import random
import uuid
from datetime import datetime, timedelta

import polars as pl


INTENT_PROFILES = {
    "BROWSE": {
        "actions": ["page_view"] * 8 + ["search_query"] * 2,
        "cart_adds": 0,
        "checkouts": 0,
        "value_range": (0, 0),
        "categories": 4,
    },
    "COMPARE": {
        "actions": ["page_view"] * 6 + ["search_query"] * 3 + ["filter_apply"] * 1,
        "cart_adds": 0,
        "checkouts": 0,
        "value_range": (0, 0),
        "categories": 5,
    },
    "CART_BUILDER": {
        "actions": ["page_view"] * 3 + ["add_to_cart"] * 4 + ["search_query"] * 1,
        "cart_adds": 4,
        "checkouts": 0,
        "value_range": (60, 200),
        "categories": 2,
    },
    "CHECKOUT_INTENT": {
        "actions": ["page_view"] * 2 + ["add_to_cart"] * 2 + ["checkout_start"] * 1,
        "cart_adds": 2,
        "checkouts": 1,
        "value_range": (120, 500),
        "categories": 1,
    },
    "PRICE_SENSITIVE": {
        "actions": ["search_query"] * 5 + ["page_view"] * 2 + ["add_to_cart"] * 1 + ["remove_from_cart"] * 2,
        "cart_adds": 1,
        "checkouts": 0,
        "value_range": (20, 80),
        "categories": 3,
    },
    "CHURN_RISK": {
        "actions": ["page_view"] * 2,
        "cart_adds": 0,
        "checkouts": 0,
        "value_range": (0, 0),
        "categories": 1,
        "long_session": True,
    },
    "LOYAL_RETURNER": {
        "actions": ["page_view"] * 1 + ["add_to_cart"] * 1 + ["checkout_start"] * 1,
        "cart_adds": 1,
        "checkouts": 1,
        "value_range": (150, 400),
        "categories": 1,
        "repeat_customer": True,
    },
}


def generate_session(intent: str, session_id: str, start_time: datetime) -> list[dict]:
    profile = INTENT_PROFILES[intent]
    actions = profile["actions"].copy()
    random.shuffle(actions)

    events = []
    current_time = start_time
    categories = [f"cat_{i}" for i in range(profile["categories"])]
    value = random.randint(*profile["value_range"]) if profile["value_range"][1] > 0 else 0

    for i, action in enumerate(actions):
        current_time += timedelta(seconds=random.randint(10, 120))
        event = {
            "event_id": str(uuid.uuid4())[:12],
            "session_id": session_id,
            "customer_id": f"cust_{random.randint(1, 1000)}",
            "timestamp": current_time.isoformat(),
            "action": action,
            "product_id": f"prod_{random.randint(1, 500)}",
            "category": random.choice(categories),
            "value": value if action in ("add_to_cart", "checkout_start", "purchase_complete") else None,
            "metadata": json.dumps({}),  # Flattened for CSV
        }
        if action == "search_query":
            event["metadata"] = json.dumps({"query": f"search for {random.choice(categories)}"})
        events.append(event)

    if profile.get("long_session"):
        events[-1]["timestamp"] = (start_time + timedelta(minutes=12)).isoformat()

    return events


def generate_dataset(n_sessions: int = 5000, output_path: str = "data/synthetic_clicks.csv") -> None:
    random.seed(42)
    all_events = []
    intents = list(INTENT_PROFILES.keys())
    start_base = datetime(2024, 1, 1)

    for i in range(n_sessions):
        intent = random.choice(intents)
        session_id = f"sess_{i:06d}"
        start_time = start_base + timedelta(minutes=random.randint(0, 60 * 24 * 30))
        events = generate_session(intent, session_id, start_time)
        for e in events:
            e["ground_truth_intent"] = intent
        all_events.extend(events)

    df = pl.DataFrame(all_events)
    os.makedirs("data", exist_ok=True)
    df.write_csv(output_path)
    print(f"Generated {len(all_events)} events across {n_sessions} sessions → {output_path}")
    print(df.group_by("ground_truth_intent").agg(pl.len()).sort("len", descending=True))


if __name__ == "__main__":
    generate_dataset()
