"""
System 2 Planner Agent
=======================
LLM-powered agent for complex intent resolution.

Uses a local open-source model (Llama 3 via Ollama/vLLM) with GraphRAG
tools to analyze ambiguous sessions and recommend interventions.

The planner is invoked when System 1 confidence is below the threshold,
indicating the ML ensemble cannot confidently classify the intent.
"""

import asyncio
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
from loguru import logger

from src.agents.tools.graph_retriever import get_customer_affinity, query_product_graph
from src.config import settings


def _extract_first_json(text: str) -> str | None:
    """Extract the first balanced JSON object from text using brace-depth counting."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None

# Lazy-initialized LLM
_llm = None

PLANNER_TIMEOUT_SECONDS = 30.0
MAX_TOOL_ROUNDS = 5


def _strip_v1_suffix(url: str) -> str:
    """Strip /v1 suffix from a URL using proper URL parsing."""
    from urllib.parse import urlparse, urlunsplit

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


PLANNER_SYSTEM_PROMPT = """You are an e-commerce intent resolver and customer intervention planner.

Your role is to analyze ambiguous user sessions and recommend the best intervention action.

## Context You Receive
- Session ID and customer ID
- Recent click/event history
- ML ensemble classification (may be low-confidence)
- Product graph context (from knowledge graph)
- Customer affinity data (from purchase history)

## Your Task
1. Analyze the session behavior pattern (e.g., rapid category switching, cart abandonment signals)
2. Use the query_product_graph tool to find relevant products and cross-sell opportunities
3. Use the get_customer_affinity tool to understand the customer's preferences
4. Recommend ONE of these intervention actions:
   - OFFER_BUNDLE: Suggest a product bundle based on category affinity
   - SEND_ABANDON_EMAIL: Trigger cart abandonment recovery
   - OFFER_DISCOUNT: Offer a targeted discount to close the sale
   - SEND_TO_HUMAN: Escalate to human support for complex cases
   - NO_ACTION: No intervention needed (customer is browsing normally)
   - SHOW_URGENCY: Create urgency (limited stock, flash sale)

## Response Format
Always respond with a JSON object:
{
  "action": "<ACTION_NAME>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<brief explanation>",
  "product_context": "<relevant products from graph>",
  "customer_segment": "<identified segment>"
}
"""

PLANNER_PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessage(content="{input}"),
    ]
)

# Tools available to the planner
PLANNER_TOOLS: list[BaseTool] = [query_product_graph, get_customer_affinity]


def _get_llm():
    """Get or create the LLM client."""
    global _llm
    if _llm is None:
        if settings.llm_provider == "ollama":
            import warnings

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=DeprecationWarning)
                from langchain_ollama import ChatOllama

            _llm = ChatOllama(
                model=settings.llm_model,
                base_url=_strip_v1_suffix(settings.llm_base_url),
            )
        else:
            from langchain_openai import ChatOpenAI

            _llm = ChatOpenAI(
                model=settings.llm_model,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                temperature=0.3,
                max_tokens=1024,
            )
        logger.info(f"LLM initialized: {settings.llm_provider}/{settings.llm_model}")
    return _llm


def build_planner_input(
    session_id: str,
    customer_id: str | None,
    intent: str,
    confidence: float,
    recent_events: list[dict],
    features: dict,
) -> str:
    """
    Build the natural language input for the planner agent.

    Args:
        session_id: The session identifier.
        customer_id: The customer identifier (if known).
        intent: The ML ensemble's intent prediction.
        confidence: The ML ensemble's confidence score.
        recent_events: List of recent click events (dicts).
        features: Engineered session features.

    Returns:
        Formatted string for the planner LLM.
    """
    events_summary = "\n".join(
        f"  - {e.get('action', 'unknown')} on {e.get('product_id', 'N/A')} "
        f"(category: {e.get('category', 'N/A')}, value: ${e.get('value', 0):.2f})"
        for e in recent_events[-10:]  # Last 10 events
    )

    return f"""Analyze this e-commerce session and recommend an intervention:

Session: {session_id}
Customer: {customer_id or "anonymous"}
ML Intent: {intent} (confidence: {confidence:.2f})

Recent Events:
{events_summary if events_summary else "  No recent events"}

Session Features:
- Duration: {features.get("session_duration_sec", 0):.0f}s
- Total actions: {features.get("total_actions", 0)}
- Cart value: ${features.get("total_cart_value", 0):.2f}
- Cart adds: {features.get("cart_adds", 0)}
- Checkouts: {features.get("checkouts", 0)}
- Category switches: {features.get("category_switches", 0)}
- Exploration ratio: {features.get("exploration_ratio", 0):.2f}

Please:
1. Use query_product_graph to find products in the session's categories
{"2. Use get_customer_affinity to check this customer's purchase history" if customer_id else
 "2. Note: customer is anonymous, no affinity data available"}
3. Recommend the best intervention action"""


async def run_planner(
    session_id: str,
    customer_id: str | None,
    intent: str,
    confidence: float,
    recent_events: list[dict],
    features: dict,
) -> dict:
    """
    Run the System 2 planner agent asynchronously.

    Args:
        session_id: The session identifier.
        customer_id: The customer identifier (if known).
        intent: The ML ensemble's intent prediction.
        confidence: The ML ensemble's confidence score.
        recent_events: List of recent click events.
        features: Engineered session features.

    Returns:
        Dict with action, confidence, reasoning, and context.
    """
    planner_input = build_planner_input(
        session_id, customer_id, intent, confidence, recent_events, features
    )

    try:
        llm = _get_llm()
        llm_with_tools = llm.bind_tools(PLANNER_TOOLS)

        messages = PLANNER_PROMPT.format_messages(
            chat_history=[],
            input=planner_input,
        )

        response = await asyncio.wait_for(
            llm_with_tools.ainvoke(messages),
            timeout=PLANNER_TIMEOUT_SECONDS,
        )

        for _ in range(MAX_TOOL_ROUNDS):
            if not response.tool_calls:
                break

            messages.append(response)

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool = next((t for t in PLANNER_TOOLS if t.name == tool_name), None)
                if tool:
                    result = await tool.ainvoke(tool_call["args"])
                    messages.append(
                        ToolMessage(
                            content=str(result),
                            tool_call_id=tool_call["id"],
                        )
                    )

            response = await asyncio.wait_for(
                llm_with_tools.ainvoke(messages),
                timeout=PLANNER_TIMEOUT_SECONDS,
            )

        output = response.content if hasattr(response, "content") else str(response)

        # Try to parse JSON from the LLM output
        try:
            # Robustly extract JSON block from LLM output (may be wrapped in markdown)
            json_str = _extract_first_json(output)
            if json_str:
                parsed = json.loads(json_str)
                return {
                    "action": parsed.get("action", "NO_ACTION"),
                    "confidence": parsed.get("confidence", 0.5),
                    "reasoning": parsed.get("reasoning", "LLM analysis"),
                    "product_context": parsed.get("product_context", ""),
                    "customer_segment": parsed.get("customer_segment", "unknown"),
                    "source": "system_2_planner",
                }
        except json.JSONDecodeError:
            pass

        # Fallback: extract action from plain text
        action = "NO_ACTION"
        if "OFFER_BUNDLE" in output:
            action = "OFFER_BUNDLE"
        elif "SEND_ABANDON_EMAIL" in output:
            action = "SEND_ABANDON_EMAIL"
        elif "OFFER_DISCOUNT" in output:
            action = "OFFER_DISCOUNT"
        elif "SEND_TO_HUMAN" in output:
            action = "SEND_TO_HUMAN"
        elif "SHOW_URGENCY" in output:
            action = "SHOW_URGENCY"

        return {
            "action": action,
            "confidence": 0.6,
            "reasoning": output[:500],
            "product_context": "",
            "customer_segment": "unknown",
            "source": "system_2_planner",
        }

    except Exception as e:
        logger.error(f"Planner agent failed for session {session_id}: {e}")
        return {
            "action": "NO_ACTION",
            "confidence": 0.0,
            "reasoning": f"Planner error: {str(e)[:200]}",
            "product_context": "",
            "customer_segment": "unknown",
            "source": "system_2_error",
        }


async def close_planner():
    """Clean up planner resources."""
    global _llm
    from src.agents.tools.graph_retriever import close_driver

    await close_driver()
    _llm = None
    logger.info("Planner agent closed")
