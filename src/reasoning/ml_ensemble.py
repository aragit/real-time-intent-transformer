import os
from typing import Tuple, Optional

import joblib
import numpy as np
from loguru import logger

from src.config import settings
from src.models.features import SessionFeatures
from src.reasoning.rule_classifier import RuleBasedClassifier


class MLEnsembleClassifier:
    """
    sklearn RandomForest/XGBoost ensemble.
    Falls back to rule-based if model not found or confidence too low.
    """

    FEATURE_ORDER = [
        "session_duration_sec",
        "total_actions",
        "page_views",
        "cart_adds",
        "cart_removes",
        "checkouts",
        "searches",
        "total_cart_value",
        "max_item_value",
        "avg_item_value",
        "categories_viewed",
        "category_switches",
        "cart_conversion_rate",
        "checkout_conversion_rate",
        "cart_abandon_rate",
        "exploration_ratio",
        "cart_value_per_minute",
        "avg_inter_event_time",
    ]

    def __init__(self):
        self.model = None
        self.rule_classifier = RuleBasedClassifier()
        self._load_model()

    def _load_model(self) -> None:
        path = settings.model_path
        if os.path.exists(path):
            try:
                self.model = joblib.load(path)
                logger.info(f"Loaded ML model from {path}")
            except Exception as e:
                logger.warning(f"Failed to load model: {e}")
        else:
            logger.warning(f"No model found at {path}. Using rule-based fallback.")

    def _vectorize(self, features: SessionFeatures) -> np.ndarray:
        return np.array([
            getattr(features, name, 0.0) for name in self.FEATURE_ORDER
        ]).reshape(1, -1)

    def classify(self, features: SessionFeatures) -> Tuple[str, float, str]:
        """
        Returns (intent, confidence, method).
        """
        # Try rule-based first
        intent, confidence = self.rule_classifier.classify(features)
        if confidence >= 0.6:
            return intent, confidence, "rule_based"

        # Fallback to ML if available
        if self.model is not None:
            try:
                vector = self._vectorize(features)
                proba = self.model.predict_proba(vector)[0]
                idx = int(np.argmax(proba))
                intent = self.model.classes_[idx]
                confidence = float(proba[idx])
                return intent, confidence, "ml_ensemble"
            except Exception as e:
                logger.error(f"ML inference failed: {e}")

        return intent, confidence, "rule_based"
