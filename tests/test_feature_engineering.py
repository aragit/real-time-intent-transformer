from datetime import datetime

from src.models.events import ClickEvent
from src.perception.feature_engineer import FeatureEngineer


class TestFeatureEngineer:
    def test_empty_session(self):
        engineer = FeatureEngineer()
        features = engineer.engineer([])
        assert features.session_id == "empty"

    def test_single_page_view(self):
        engineer = FeatureEngineer()
        events = [ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 0))]
        features = engineer.engineer(events)
        assert features.page_views == 1
        assert features.cart_adds == 0
        assert features.session_duration_sec == 0

    def test_cart_adds_and_removes(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="add_to_cart", value=50, timestamp=datetime(2024, 1, 1, 12, 1)),
            ClickEvent(session_id="s1", action="remove_from_cart", value=50, timestamp=datetime(2024, 1, 1, 12, 2)),
        ]
        features = engineer.engineer(events)
        assert features.cart_adds == 1
        assert features.cart_removes == 1
        assert features.cart_abandon_rate == 0.5  # 1 remove / (1 add + 1) = 0.5

    def test_session_duration(self):
        engineer = FeatureEngineer()
        start = datetime(2024, 1, 1, 12, 0)
        end = datetime(2024, 1, 1, 12, 10)
        events = [
            ClickEvent(session_id="s1", action="page_view", timestamp=start),
            ClickEvent(session_id="s1", action="checkout_start", timestamp=end),
        ]
        features = engineer.engineer(events)
        assert features.session_duration_sec == 600.0

    def test_category_switching(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="page_view", category="A", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="page_view", category="B", timestamp=datetime(2024, 1, 1, 12, 1)),
            ClickEvent(session_id="s1", action="page_view", category="A", timestamp=datetime(2024, 1, 1, 12, 2)),
        ]
        features = engineer.engineer(events)
        assert features.categories_viewed == 2
        assert features.category_switches == 2

    def test_cart_value_per_minute(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="add_to_cart", value=120, timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="add_to_cart", value=120, timestamp=datetime(2024, 1, 1, 12, 4)),
        ]
        features = engineer.engineer(events)
        assert features.total_cart_value == 240
        assert features.cart_value_per_minute == 240 / 5  # 4 min + 1 buffer

    def test_exploration_ratio(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="page_view", category="A", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="page_view", category="B", timestamp=datetime(2024, 1, 1, 12, 1)),
            ClickEvent(session_id="s1", action="page_view", category="C", timestamp=datetime(2024, 1, 1, 12, 2)),
        ]
        features = engineer.engineer(events)
        assert features.exploration_ratio == 2 / 4  # 2 switches / (3 views + 1)

    def test_action_sequence_order(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="search_query", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 1)),
            ClickEvent(session_id="s1", action="add_to_cart", timestamp=datetime(2024, 1, 1, 12, 2)),
        ]
        features = engineer.engineer(events)
        assert features.action_sequence == ["search_query", "page_view", "add_to_cart"]

    def test_checkout_conversion_rate(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="add_to_cart", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="add_to_cart", timestamp=datetime(2024, 1, 1, 12, 1)),
            ClickEvent(session_id="s1", action="checkout_start", timestamp=datetime(2024, 1, 1, 12, 2)),
        ]
        features = engineer.engineer(events)
        assert features.checkout_conversion_rate == 1 / 3

    def test_avg_inter_event_time(self):
        engineer = FeatureEngineer()
        events = [
            ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 0)),
            ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 0, 30)),
            ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 1, 0)),
        ]
        features = engineer.engineer(events)
        assert features.avg_inter_event_time == 30.0

    def test_polars_performance_dtype(self):
        engineer = FeatureEngineer()
        events = [ClickEvent(session_id="s1", action="page_view", timestamp=datetime(2024, 1, 1, 12, 0)) for _ in range(100)]
        features = engineer.engineer(events)
        assert features.total_actions == 100
        assert isinstance(features.page_views, int)
