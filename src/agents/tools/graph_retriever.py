"""
GraphRAG Retriever Tools
========================
LangChain tools for querying the Neo4j product knowledge graph.

These tools provide the LLM planner with structured context about:
- Product relationships (complementary, similar, bundled)
- Customer affinities and purchase patterns
- Category hierarchies and cross-sell opportunities
"""

import json

from langchain_core.tools import tool
from loguru import logger
from neo4j import AsyncGraphDatabase

from src.config import settings

# Lazy-initialized driver
_driver = None

# Per-query timeout to prevent complex traversals from hanging the agent.
NEO4J_QUERY_TIMEOUT = 5.0


async def _get_driver():
    """Get or create the async Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        logger.info(f"Neo4j driver connected to {settings.neo4j_uri}")
    return _driver


async def close_driver():
    """Close the Neo4j driver connection."""
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


@tool
async def query_product_graph(
    category: str,
    max_results: int = 5,
) -> str:
    """
    Query the product knowledge graph for related and complementary products.

    Use this tool when you need to:
    - Find products in a specific category
    - Discover complementary products for cross-selling
    - Identify product bundles and recommendations
    - Understand category hierarchies

    Args:
        category: The product category to query (e.g., "electronics", "fashion", "home").
        max_results: Maximum number of results to return (default 5).

    Returns:
        JSON string with product recommendations and relationships.
    """
    driver = await _get_driver()

    cypher = """
    MATCH (p:Product)-[:IN_CATEGORY]->(c:Category {name: $category})
    OPTIONAL MATCH (p)-[:COMPLEMENTARY_TO]->(comp:Product)
    OPTIONAL MATCH (p)-[:SIMILAR_TO]->(sim:Product)
    WITH p, COLLECT(DISTINCT comp.name)[..3] AS complementary,
         COLLECT(DISTINCT sim.name)[..3] AS similar
    RETURN p.name AS product_name,
           p.price AS price,
           p.popularity AS popularity,
           complementary,
           similar
    ORDER BY p.popularity DESC
    LIMIT $max_results
    """

    async with driver.session() as session:
        result = await session.run(
            cypher, category=category, max_results=max_results, timeout=NEO4J_QUERY_TIMEOUT
        )
        records = [dict(record) async for record in result]

    if not records:
        return json.dumps(
            {
                "category": category,
                "products": [],
                "message": f"No products found in category '{category}'. The knowledge graph may need seeding.",
            }
        )

    return json.dumps(
        {
            "category": category,
            "products": records,
            "total_found": len(records),
        },
        default=str,
    )


@tool
async def get_customer_affinity(
    customer_id: str,
    max_categories: int = 5,
) -> str:
    """
    Query customer purchase history and category affinities from the knowledge graph.

    Use this tool when you need to:
    - Understand a customer's purchase patterns
    - Find what categories a customer prefers
    - Identify cross-sell opportunities based on past behavior
    - Detect churn risk signals from declining engagement

    Args:
        customer_id: The customer identifier to look up.
        max_categories: Maximum number of preferred categories to return (default 5).

    Returns:
        JSON string with customer affinity data and purchase history.
    """
    driver = await _get_driver()

    cypher = """
    MATCH (cust:Customer {id: $customer_id})-[:PURCHASED]->(p:Product)-[:IN_CATEGORY]->(c:Category)
    WITH c.name AS category, COUNT(p) AS purchase_count, SUM(p.price) AS total_spent
    ORDER BY purchase_count DESC
    LIMIT $max_categories
    RETURN category, purchase_count, total_spent
    """

    async with driver.session() as session:
        result = await session.run(
            cypher,
            customer_id=customer_id,
            max_categories=max_categories,
            timeout=NEO4J_QUERY_TIMEOUT,
        )
        records = [dict(record) async for record in result]

    if not records:
        return json.dumps(
            {
                "customer_id": customer_id,
                "affinities": [],
                "message": f"No purchase history found for customer '{customer_id}'.",
            }
        )

    return json.dumps(
        {
            "customer_id": customer_id,
            "affinities": records,
            "top_category": records[0]["category"] if records else None,
            "total_categories": len(records),
        },
        default=str,
    )
