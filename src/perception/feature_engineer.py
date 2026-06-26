from typing import List

import polars as pl
from loguru import logger

from src.models.events import ClickEvent
from src.models.features import SessionFeatures


class FeatureEngineer:
    """Engineer behavioral features from session events using Polars."""

    def engineer(self, events: List[ClickEvent]) -> SessionFeatures:
        if not events:
            return SessionFeatures(session_id="empty")

        # Sort by timestamp
        events = sorted(events, key=lambda e: e.timestamp)
        session_id = events[0].session_id
        customer_id = events[0].customer_id

        # Build Polars DataFrame
        df = pl.DataFrame(
            {
                "timestamp": [e.timestamp for e in events],
                "action": [e.action for e in events],
                "category": [e.category or "unknown" for e in events],
                "value": [e.value or 0.0 for e in events],
            }
        )

        # Time-based
        session_start = df["timestamp"].min()
        session_end = df["timestamp"].max()
        session_duration_sec = (session_end - session_start).total_seconds()
        avg_inter_event_time = (
            df["timestamp"].diff().mean().total_seconds() if len(events) > 1 else 0.0
        )

        # Frequency-based
        total_actions = len(events)
        page_views = (df["action"] == "page_view").sum()
        cart_adds = (df["action"] == "add_to_cart").sum()
        cart_removes = (df["action"] == "remove_from_cart").sum()
        checkouts = (df["action"] == "checkout_start").sum()
        searches = (df["action"] == "search_query").sum()

        # Value-based
        total_cart_value = df["value"].sum()
        max_item_value = df["value"].max()
        avg_item_value = total_cart_value / total_actions if total_actions > 0 else 0.0

        # Sequence-based
        categories_viewed = df["category"].n_unique()
        category_switches = (df["category"] != df["category"].shift(1)).sum()

        # Velocity-based
        minutes = (session_duration_sec / 60.0) + 1.0
        cart_value_per_minute = total_cart_value / minutes

        # Derived
        cart_conversion_rate = cart_adds / (page_views + 1)
        checkout_conversion_rate = checkouts / (cart_adds + 1)
        cart_abandon_rate = cart_removes / (cart_adds + 1) if cart_adds > 0 else 0.0
        exploration_ratio = category_switches / (page_views + 1)

        action_sequence = df["action"].to_list()

        return SessionFeatures(
            session_id=session_id,
            customer_id=customer_id,
            session_duration_sec=session_duration_sec,
            total_actions=total_actions,
            page_views=page_views,
            cart_adds=cart_adds,
            cart_removes=cart_removes,
            checkouts=checkouts,
            searches=searches,
            total_cart_value=total_cart_value,
            max_item_value=max_item_value,
            avg_item_value=avg_item_value,
            categories_viewed=categories_viewed,
            category_switches=category_switches,
            cart_conversion_rate=cart_conversion_rate,
            checkout_conversion_rate=checkout_conversion_rate,
            cart_abandon_rate=cart_abandon_rate,
            exploration_ratio=exploration_ratio,
            cart_value_per_minute=cart_value_per_minute,
            avg_inter_event_time=avg_inter_event_time,
            action_sequence=action_sequence,
        )
