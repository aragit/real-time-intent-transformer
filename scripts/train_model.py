#!/usr/bin/env python3
"""
Train sklearn RandomForest on synthetic clickstream data.
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import joblib
import polars as pl
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

from src.perception.feature_engineer import FeatureEngineer
from src.models.events import ClickEvent


def load_events(path: str = "data/synthetic_clicks.csv") -> pl.DataFrame:
    return pl.read_csv(path)


def events_to_features(df: pl.DataFrame) -> tuple:
    engineer = FeatureEngineer()
    sessions = df.group_by("session_id").agg(pl.all().sort_by("timestamp"))

    X, y = [], []
    for session in sessions.iter_rows(named=True):
        events = []
        n_events = len(session["event_id"])
        for i in range(n_events):
            events.append(ClickEvent(
                event_id=session["event_id"][i],
                session_id=session["session_id"],
                customer_id=session["customer_id"][i],
                timestamp=session["timestamp"][i],
                action=session["action"][i],
                product_id=session["product_id"][i],
                category=session["category"][i],
                value=session["value"][i] if session["value"][i] is not None else None,
                metadata=json.loads(session["metadata"][i]) if session["metadata"][i] else {},
            ))
        features = engineer.engineer(events)
        X.append([
            features.session_duration_sec,
            features.total_actions,
            features.page_views,
            features.cart_adds,
            features.cart_removes,
            features.checkouts,
            features.searches,
            features.total_cart_value,
            features.max_item_value,
            features.avg_item_value,
            features.categories_viewed,
            features.category_switches,
            features.cart_conversion_rate,
            features.checkout_conversion_rate,
            features.cart_abandon_rate,
            features.exploration_ratio,
            features.cart_value_per_minute,
            features.avg_inter_event_time,
        ])
        y.append(session["ground_truth_intent"][0])

    return X, y


def train():
    os.makedirs("models", exist_ok=True)
    df = load_events()
    X, y = events_to_features(df)

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    clf = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print(classification_report(y_test, y_pred))

    joblib.dump(clf, "models/intent_classifier.joblib")
    print("Model saved to models/intent_classifier.joblib")


if __name__ == "__main__":
    train()
