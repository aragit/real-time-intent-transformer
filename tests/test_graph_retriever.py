"""
GraphRAG Retriever Tool Tests
==============================
Tests for the Neo4j GraphRAG tools with mocked database connections.

Verifies that:
- Cypher queries execute correctly against mock data
- Results are properly formatted as JSON for the LLM
- Empty results return appropriate fallback messages
- Tool signatures match LangChain @tool expectations
"""

import json
from unittest.mock import patch

import pytest

from src.agents.tools.graph_retriever import get_customer_affinity, query_product_graph

# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


class MockRecord:
    """Simulates a Neo4j record."""

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def keys(self):
        return self._data.keys()


class MockAsyncIterator:
    """Async iterator for mock Neo4j results."""

    def __init__(self, items):
        self._items = items
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


class MockResult:
    """Simulates a Neo4j async result."""

    def __init__(self, records: list[dict]):
        self._records = [MockRecord(r) for r in records]

    def __aiter__(self):
        return MockAsyncIterator(self._records)


class MockSession:
    """Simulates a Neo4j async session."""

    def __init__(self, records: list[dict]):
        self._records = records

    async def run(self, query: str, **kwargs) -> MockResult:
        return MockResult(self._records)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class MockDriver:
    """Simulates a Neo4j async driver."""

    def __init__(self, records: list[dict]):
        self._records = records

    def session(self):
        return MockSession(self._records)

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# query_product_graph tests
# ---------------------------------------------------------------------------


class TestQueryProductGraph:
    @pytest.mark.asyncio
    async def test_returns_formatted_json(self):
        mock_records = [
            {
                "product_name": "MacBook Pro",
                "price": 1999.99,
                "popularity": 95,
                "complementary": ["USB-C Hub", "Laptop Stand"],
                "similar": ["ThinkPad X1"],
            },
            {
                "product_name": "Dell XPS 15",
                "price": 1499.99,
                "popularity": 88,
                "complementary": ["Wireless Mouse"],
                "similar": ["MacBook Air"],
            },
        ]

        mock_driver = MockDriver(mock_records)
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await query_product_graph.ainvoke({"category": "laptops"})

        parsed = json.loads(result)
        assert parsed["category"] == "laptops"
        assert parsed["total_found"] == 2
        assert len(parsed["products"]) == 2
        assert parsed["products"][0]["product_name"] == "MacBook Pro"
        assert parsed["products"][0]["price"] == 1999.99
        assert "USB-C Hub" in parsed["products"][0]["complementary"]

    @pytest.mark.asyncio
    async def test_empty_results_returns_fallback(self):
        mock_driver = MockDriver([])
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await query_product_graph.ainvoke({"category": "nonexistent"})

        parsed = json.loads(result)
        assert parsed["category"] == "nonexistent"
        assert parsed["products"] == []
        assert "No products found" in parsed["message"]

    @pytest.mark.asyncio
    async def test_respects_max_results_parameter(self):
        mock_records = [
            {
                "product_name": f"Product {i}",
                "price": i * 10,
                "popularity": i,
                "complementary": [],
                "similar": [],
            }
            for i in range(10)
        ]
        mock_driver = MockDriver(mock_records)

        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await query_product_graph.ainvoke(
                {"category": "electronics", "max_results": 3}
            )

        parsed = json.loads(result)
        assert parsed["total_found"] == 10

    @pytest.mark.asyncio
    async def test_tool_has_correct_name(self):
        assert query_product_graph.name == "query_product_graph"

    @pytest.mark.asyncio
    async def test_tool_has_description(self):
        assert "product" in query_product_graph.description.lower()

    @pytest.mark.asyncio
    async def test_handles_none_complementary(self):
        mock_records = [
            {
                "product_name": "Standalone Item",
                "price": 49.99,
                "popularity": 50,
                "complementary": [],
                "similar": [],
            },
        ]
        mock_driver = MockDriver(mock_records)
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await query_product_graph.ainvoke({"category": "accessories"})

        parsed = json.loads(result)
        assert parsed["products"][0]["complementary"] == []


# ---------------------------------------------------------------------------
# get_customer_affinity tests
# ---------------------------------------------------------------------------


class TestGetCustomerAffinity:
    @pytest.mark.asyncio
    async def test_returns_formatted_json(self):
        mock_records = [
            {"category": "electronics", "purchase_count": 5, "total_spent": 2499.95},
            {"category": "fashion", "purchase_count": 3, "total_spent": 450.00},
        ]

        mock_driver = MockDriver(mock_records)
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await get_customer_affinity.ainvoke({"customer_id": "cust_001"})

        parsed = json.loads(result)
        assert parsed["customer_id"] == "cust_001"
        assert parsed["top_category"] == "electronics"
        assert parsed["total_categories"] == 2
        assert parsed["affinities"][0]["purchase_count"] == 5

    @pytest.mark.asyncio
    async def test_empty_results_returns_fallback(self):
        mock_driver = MockDriver([])
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await get_customer_affinity.ainvoke({"customer_id": "new_customer"})

        parsed = json.loads(result)
        assert parsed["customer_id"] == "new_customer"
        assert parsed["affinities"] == []
        assert "No purchase history" in parsed["message"]

    @pytest.mark.asyncio
    async def test_tool_has_correct_name(self):
        assert get_customer_affinity.name == "get_customer_affinity"

    @pytest.mark.asyncio
    async def test_tool_has_description(self):
        assert "customer" in get_customer_affinity.description.lower()

    @pytest.mark.asyncio
    async def test_single_category_result(self):
        mock_records = [
            {"category": "home", "purchase_count": 1, "total_spent": 89.99},
        ]
        mock_driver = MockDriver(mock_records)
        with patch("src.agents.tools.graph_retriever._get_driver", return_value=mock_driver):
            result = await get_customer_affinity.ainvoke({"customer_id": "cust_single"})

        parsed = json.loads(result)
        assert parsed["top_category"] == "home"
        assert parsed["total_categories"] == 1
