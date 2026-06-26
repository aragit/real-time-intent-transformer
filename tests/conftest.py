import pytest
from datetime import datetime

from src.models.events import ClickEvent


@pytest.fixture
def sample_event():
    return ClickEvent(
        session_id="sess_001",
        customer_id="cust_001",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        action="page_view",
        product_id="prod_001",
        category="electronics",
        value=None,
    )


@pytest.fixture
def cart_event():
    return ClickEvent(
        session_id="sess_001",
        customer_id="cust_001",
        timestamp=datetime(2024, 1, 1, 12, 1, 0),
        action="add_to_cart",
        product_id="prod_001",
        category="electronics",
        value=99.99,
    )


@pytest.fixture
def checkout_event():
    return ClickEvent(
        session_id="sess_001",
        customer_id="cust_001",
        timestamp=datetime(2024, 1, 1, 12, 5, 0),
        action="checkout_start",
        product_id="prod_001",
        category="electronics",
        value=99.99,
    )
